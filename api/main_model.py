"""Saved synthetic model used by the dashboard; no fitting or personal-log access."""
from __future__ import annotations

import hashlib
import json
import os
from functools import lru_cache
from pathlib import Path
from dataclasses import replace

from engine.src.config import POSITION_CFG, TIME_CFG
from engine.src.geo import haversine_m
from engine.src.ml.insights import _rain_now
from engine.src.scorers._common import reposition_for
from engine.src.timeutil import parse_local
from engine.src.types import DirectionPlan, ObjectiveResult, PlanStep, PositionCandidate, TripValueCandidate

ROOT = Path(__file__).resolve().parents[1]
MODEL_NAME = 'logistic-hazard-quantile-gb'


@lru_cache(maxsize=2)
def load_saved_model(directory):
    import joblib
    import sklearn
    folder = Path(directory)
    report = json.loads((folder/'report.json').read_text(encoding='utf8'))
    artifact = folder/'models.joblib'
    if hashlib.sha256(artifact.read_bytes()).hexdigest() != report['artifact_sha256']:
        raise ValueError('Model hash không khớp report.json.')
    if report['versions']['sklearn'] != sklearn.__version__:
        raise ValueError('Phiên bản scikit-learn không khớp bản train model.')
    if report.get('kind') != 'synthetic_research_only':
        raise ValueError('Model không đúng provenance đã chốt.')
    catalog = json.loads((folder/'catalog.json').read_text(encoding='utf8'))
    if catalog['artifact_sha256'] != report['artifact_sha256']:
        raise ValueError('Catalog không thuộc model này.')
    # Trusted administrator-owned artifact only. Never accept a client-supplied path.
    model = joblib.load(artifact)
    if not all(model['development_gate'].get(k) for k in ('wait', 'cycle')):
        raise ValueError('Model chưa vượt development gate.')
    return model, report, catalog


def apply_main_model(output, data, ctx, prefs, *, use_poi=False, use_live_candidates=False):
    """Replace earning objectives, leaving weather/rest/traffic provider results intact."""
    from engine.src.priority import build_priority
    from engine.src.tradeoff import build_tradeoff_matrix
    directory = os.environ.get('GIGCA_MAIN_MODEL_DIR', str(ROOT/'.cache/models'/'logistic-hazard-quantile-gb-hcmc'))
    source = 'synthetic_base_model'
    note = ('Model chung học từ dữ liệu mô phỏng, không phải lịch sử của bạn. '
            'Năng suất cho một chu kỳ chờ + chuyến; chưa tính đầy đủ đi đón/chuyển vùng. '
            'Điểm neo không xác nhận chỗ đỗ/chờ hợp lệ.')
    info = {'source': source, 'model_name': MODEL_NAME, 'status': 'unavailable', 'notes': [note],
            'wait_model': {'used': False, 'backtest': {'status': 'unavailable'}, 'zones': []},
            'cycle_yield': {'backtest': {'status': 'unavailable'}, 'zones': []}, 'areas': []}
    objectives = dict(output.objectives)
    try:
        model, report, catalog = load_saved_model(str(Path(directory).resolve()))
        coverage_text = f"{report['test']['cycle_coverage']*100:.1f}".replace('.', ',')
        nominal = round((1-report.get('config',{}).get('conformal_alpha',.2))*100)
        note += f' Khoảng danh nghĩa {nominal}% đạt độ phủ kiểm tra khoảng {coverage_text}%.'
        info['notes'][0] = note
        now = parse_local(data.generated_at, int(TIME_CFG['local_utc_offset_minutes']))
        if now is None:
            raise ValueError('Thiếu thời điểm hợp lệ để dự đoán.')
        anchors = [{**a, 'name': a['name'].replace(' - điểm neo giả định', '')} for a in catalog['areas']]
        nearest = min(haversine_m(ctx.current_lat, ctx.current_lng, a['lat'], a['lng']) for a in anchors)
        if nearest > 2000:
            raise ValueError('Vị trí nằm ngoài vùng phủ mô phỏng của model (cách điểm neo hơn 2 km).')
        if now.hour not in catalog['training_hours']:
            raise ValueError('Giờ hiện tại ngoài các giờ đã có dữ liệu train.')
        rain = _rain_now(data, now)
        if rain is None:
            info['notes'].append('Thiếu lượng mưa cho giờ hiện tại; đặc trưng model tạm dùng 0 mm như khi train.')
        if rain is not None and not 0 <= rain <= 8:
            raise ValueError('Lượng mưa nằm ngoài miền đặc trưng model 0–8 mm.')
        areas = [{'id': 'model_current', 'name': 'Vị trí hiện tại', 'lat': ctx.current_lat, 'lng': ctx.current_lng}, *anchors]
        if use_live_candidates:
            from api.live_candidates import discover
            try:
                live_areas, discovery = discover(ctx, anchors)
                # Do not mix fixed named anchors into live destination rankings.
                areas = [areas[0], *live_areas]
                info['candidate_discovery'] = discovery
                info['notes'].append('Điểm đến lấy từ POI API quanh vị trí đã chọn; điểm neo chỉ kiểm tra miền hỗ trợ. POI không xác nhận chỗ đỗ hoặc nhu cầu có khách.')
            except Exception:
                areas = [areas[0]]
                info['candidate_discovery'] = {'status': 'provider_unavailable', 'source': 'TomTom Nearby Search'}
                info['notes'].append('Không lấy được điểm đến trực tiếp; chỉ đánh giá vị trí hiện tại, không tự thay bằng các điểm neo cố định.')
        poi_contexts={};poi_active=False
        rows = []
        thresholds = list(POSITION_CFG['wait_thresholds_min'])
        for area in areas:
            straight = haversine_m(ctx.current_lat, ctx.current_lng, area['lat'], area['lng'])
            rep = reposition_for(straight, {'at_area_radius_m': 0}
                if area.get('candidate_source') == 'tomtom_live' else None)
            if rep.km > ctx.max_reposition_km:
                continue
            wp = model['wait_model'].predict(now, area['lat'], area['lng'], rain, thresholds)
            yp = model['cycle_model'].predict(now, area['lat'], area['lng'], rain)
            if yp['median'] <= 0:
                continue
            probabilities = {k: round(v*100, 1) for k,v in wp['p_le'].items()}
            score = max(0, min(100, probabilities[str(int(thresholds[0]))]
                - float(POSITION_CFG['wait_penalty_per_min'])*wp['expected_wait_min']
                - float(POSITION_CFG['reposition_penalty_per_km'])*rep.km))
            rows.append((area, wp, yp, probabilities, rep, score))
        if not rows:
            raise ValueError('Không có điểm ứng viên phù hợp trong phạm vi di chuyển.')
        ranking={}
        if use_poi:
            from api.poi_policy import build_contexts, rank_values, policy
            cfg=policy()
            best_income=max(r[2]['median'] for r in rows);best_position=max(r[5] for r in rows)
            near_income=lambda r:r[2]['median']>=best_income*(1-cfg['income_near_tie_fraction'])
            near_position=lambda r:r[5]>=best_position-cfg['position_near_tie_points']
            leaders=[max(rows,key=lambda r:r[2]['median']),max(rows,key=lambda r:r[5])]
            shortlist=[rows[0][0]]
            for row in [*leaders,*sorted(rows,key=lambda r:r[4].km)]:
                if (near_income(row) or near_position(row)) and row[0]['id'] not in {a['id'] for a in shortlist}:shortlist.append(row[0])
            try:
                _,poi_contexts,poi_active=build_contexts(shortlist,ctx,now,anchors)
            except Exception:poi_contexts={}
            info['poi_ranking']={'enabled':poi_active,'status':'secondary_tiebreak' if poi_active else 'provider_unavailable_base_ranking',
                'kind':'experimental_manual_policy','areas':{k:{f:v for f,v in c.items() if f!='groups'} for k,c in poi_contexts.items()}}
            if poi_active:
                info['notes'].append('Giữ tiêu chí xếp hạng ML gốc; POI chỉ điều chỉnh nhẹ các phương án gần tương đương, không thay dự đoán.')
                for a,w,y,p,rep,score in rows:
                    values=rank_values(y['median'],score,rep,poi_contexts.get(a['id'],poi_contexts['model_current']),poi_contexts['model_current'],ctx.horizon_min)
                    if not near_income((a,w,y,p,rep,score)):values['income']=y['median']
                    if not near_position((a,w,y,p,rep,score)):values['position']=score
                    ranking[a['id']]=values
        cycle_bt = {'status': 'ok', 'calibrated': report['test']['cycle_coverage'] >= .8,
                    'n_cycles': report['counts']['train']['cycles'], 'n_test': report['counts']['test']['cycles'],
                    'coverage_conformal': report['test']['cycle_coverage'],
                    'mae_median_model_vnd': report['test']['cycle_mae_vnd_per_hour'],
                    'mae_train_mean_vnd': report['test']['cycle_mean_baseline_mae']}
        info.update(status='ok', areas=[r[0] for r in rows], artifact_sha256=report['artifact_sha256'])
        info['wait_model'] = {'used': True, 'backtest': {'status':'ok', 'passes': True,
            'n_spells': report['counts']['train']['waits']}, 'zones': [
            {'area_id':a['id'], 'p_wait_le_pct':p, 'expected_wait_min':round(w['expected_wait_min'],1),
             'median_wait_min':w['median_wait_min'], 'model':source} for a,w,y,p,rep,score in rows]}
        info['cycle_yield'] = {'backtest':cycle_bt, 'zones':[{'area_id':a['id'], **y} for a,w,y,p,rep,score in rows],
                               'interval_status':'synthetic_nominal_only'}
        for key in ('max_trip_value', 'maintain_position'):
            ranked = sorted(rows, key=lambda r:(-(ranking[r[0]['id']]['income'] if key=='max_trip_value' else ranking[r[0]['id']]['position']) if poi_active else (-r[2]['median'] if key=='max_trip_value' else -r[5]), r[4].km, r[0]['id']))
            candidates = []
            for rank, (a,w,y,p,rep,score) in enumerate(ranked,1):
                if poi_active:score=ranking[a['id']]['position']
                money = f"{y['median']:,}".replace(',', '.')
                wait_text = f"{w['expected_wait_min']:.1f}".replace('.', ',')
                explanation = (f"Năng suất ước tính cao nhất trong {len(rows)} khu vực: {money} đ/giờ, chờ khoảng {wait_text} phút."
                    if key == 'max_trip_value' and len(rows) > 1 and rank == 1 else
                    f"Ước tính {money} đ/giờ, chờ khoảng {wait_text} phút." if key == 'max_trip_value' else
                    f"Chờ khoảng {wait_text} phút; di chuyển ước tính {rep.km:.1f} km. "
                    + ("Điểm phù hợp cao nhất khi xét khả năng nhận cuốc, chờ và di chuyển." if rank == 1 else ""))
                if poi_active:
                    components=poi_contexts.get(a['id'],{}).get('components',[])
                    names=[component['label'] for component in components[:2]]
                    arrival=parse_local(poi_contexts.get(a['id'],{}).get('arrival_local'),int(TIME_CFG['local_utc_offset_minutes'])) or now
                    hour=arrival.hour
                    period='buổi sáng' if hour<11 else 'giữa ngày' if hour<16 else 'cuối chiều' if hour<19 else 'buổi tối'
                    context_text=('Trong khung giờ '+period+', khu vực gần '+ ' và '.join(names)+' đáng cân nhắc. ') if names else ''
                    explanation=context_text+('Ưu tiên năng suất ML dự kiến; đặc điểm khu vực theo giờ chỉ hỗ trợ khi các phương án có mức dự đoán gần nhau.' if key=='max_trip_value' else
                        ('Ở lại giúp tránh mất thời gian di chuyển; các điểm lân cận chưa có lợi thế đủ lớn.' if a['id']=='model_current' else
                         'Ưu tiên khả năng nhận cuốc, thời gian chờ và quãng đường; POI chỉ là yếu tố bổ sung.'))
                if key == 'max_trip_value':
                    candidate = TripValueCandidate(area_id=a['id'], area_name=a['name'], rank=rank,
                        yield_vnd_per_hour=y['median'], yield_low_vnd_per_hour=y['low'], yield_high_vnd_per_hour=y['high'],
                        wait_min=round(w['expected_wait_min'],1), reposition_km=round(rep.km,2),
                        reposition_min=round(rep.minutes,1), reposition_cost_vnd=round(rep.cost_vnd),
                        source_confidence='low', explanation=explanation, data_source=source)
                else:
                    candidate = PositionCandidate(area_id=a['id'], area_name=a['name'], rank=rank,
                        position_score=round(score,1), p_wait_le_pct=p[str(int(thresholds[0]))],
                        wait_threshold_min=thresholds[0], p_wait_le_by_min=p, expected_wait_min=round(w['expected_wait_min'],1),
                        median_wait_min=w['median_wait_min'], reposition_km=round(rep.km,2),
                        source_confidence='low', explanation=explanation, data_source=source)
                candidates.append(candidate)
            a,w,y,p,rep,score = ranked[0]
            if poi_active:score=ranking[a['id']]['position']
            metrics = {'data_source':source, 'yield_vnd_per_hour':y['median'], 'position_score':round(score,1),
                'p_wait_le_pct':p[str(int(thresholds[0]))], 'expected_wait_min':round(w['expected_wait_min'],1),
                'wait_min_used':round(w['expected_wait_min'],1), 'reposition_km_estimated':round(rep.km,2), 'areas_ranked':len(rows),
                'yield_interval_vnd_per_hour':[y['low'],y['high']], 'interval_status':'synthetic_nominal_only'}
            if poi_active:
                metrics.update(poi_policy=cfg['version'],
                    poi_opportunity_score=poi_contexts.get(a['id'],{}).get('score'),ranking_method='ml_poi_secondary_tiebreak',
                    ranking_score=round(ranking[a['id']]['income'] if key=='max_trip_value' else score,2),
                    effective_yield_vnd_per_hour=ranking[a['id']]['effective_yield_vnd_per_hour'],
                    horizon_net_estimated_vnd=ranking[a['id']]['horizon_net_vnd'],
                    poi_context=info['poi_ranking']['areas'].get(a['id'],{}),comparison_includes_reposition=key=='maintain_position')
            plan = DirectionPlan(key, 'Model chung · '+('Năng suất chu kỳ' if key=='max_trip_value' else 'Giữ vị trí'),
                'So sánh dự đoán từ model mô phỏng', candidates[0].explanation, a['name'],
                [PlanStep(1,'Hiện tại', f"Xem tuyến tới {a['name']}",
                    'Kiểm tra tuyến đường và chỗ dừng hợp lệ trên bản đồ trước khi di chuyển.', 'Tiếp cận điểm tham khảo'),
                 PlanStep(2,'Trong khi chờ','Theo dõi cuốc và điều kiện thực tế',
                    'Tính lại gợi ý khi vị trí hoặc thời tiết thay đổi; dự đoán không bảo đảm có cuốc.', 'Cập nhật quyết định')],
                metrics, note, 'Nếu không phù hợp thực tế, xem điểm ứng viên khác hoặc tính lại gợi ý.')
            objectives[key] = ObjectiveResult(key,'partial','low',plan=plan,candidates=candidates,caveat=note)
    except (OSError, ValueError, KeyError, ImportError, TypeError) as exc:
        reason = f'Model chung chưa dùng được: {exc}'
        info['notes'].append(reason)
        info['wait_model']['backtest']['reason'] = reason
        info['cycle_yield']['backtest']['reason'] = reason
        for key in ('max_trip_value','maintain_position'):
            objectives[key] = ObjectiveResult(key,'insufficient_data','none',reason_for_insufficiency=reason)
    return replace(output, objectives=objectives, ml_insights=info, personal_model=None,
        assumptions_used=[*output.assumptions_used,*info['notes']],
        direction_priority=build_priority(objectives,ctx,prefs),
        tradeoff_matrix=build_tradeoff_matrix(objectives,ctx,None), data_tier='synthetic_base_model',
        what_if=None, data_roadmap=None)

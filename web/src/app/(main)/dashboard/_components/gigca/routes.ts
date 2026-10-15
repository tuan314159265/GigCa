import { api } from "./api";
import { objectives, type Objective, type Place, type Recommendation } from "./types";
export interface RouteTarget {
  place: Place;
  objectives: Objective[];
}
export interface RoadRoute {
  summary: { lengthInMeters: number; travelTimeInSeconds: number };
  legs: { points: { latitude: number; longitude: number }[] }[];
  sections?: RouteSection[];
  guidance?: { instructions?: { pointIndex: number; street?: string }[] };
}
interface RouteSection {
  startPointIndex: number;
  endPointIndex: number;
  sectionType: string;
  streetName?: { text: string };
  magnitudeOfDelay?: number;
  effectiveSpeedInKmh?: number;
  delayInSeconds?: number;
}
export interface RouteRoad {
  id: string;
  name: string;
  speed: number | undefined;
  delay: number | undefined;
  status: "smooth" | "moderate" | "congested" | "unknown";
}
// Split at provider section boundaries: a jam on one part must not label the whole street.
export function routeRoads(route: RoadRoute): RouteRoad[] {
  const points = route.legs.flatMap((leg) => leg.points);
  const sections = route.sections ?? [];
  const streets = sections.filter((s) => s.sectionType === "IMPORTANT_ROAD_STRETCH");
  const traffic = sections.filter((s) => s.sectionType === "TRAFFIC");
  const instructions = route.guidance?.instructions ?? [];
  const boundaries = [...new Set([0, points.length - 1,
    ...sections.flatMap((s) => [s.startPointIndex, s.endPointIndex]),
    ...instructions.map((s) => s.pointIndex)])]
    .filter((i) => Number.isInteger(i) && i >= 0 && i < points.length).sort((a, b) => a - b);
  return boundaries.slice(0, -1).map((start, i) => {
    const end = boundaries[i + 1];
    const street = streets.find((s) => s.startPointIndex <= start && s.endPointIndex >= end);
    const instruction = instructions.filter((s) => s.pointIndex <= start && s.street).at(-1);
    const observations = traffic.filter((s) => s.startPointIndex <= start && s.endPointIndex >= end);
    const observation = observations.sort((a, b) => (b.magnitudeOfDelay ?? -1) - (a.magnitudeOfDelay ?? -1))[0];
    const magnitude = observation?.magnitudeOfDelay;
    return {
      id: `${start}:${end}`,
      name: street?.streetName?.text ?? instruction?.street ?? "Đoạn đường chưa có tên",
      speed: observation?.effectiveSpeedInKmh,
      delay: observation?.delayInSeconds,
      status: magnitude === 0 ? "smooth" : magnitude === 1 ? "moderate"
        : magnitude === 2 || magnitude === 3 || magnitude === 4 ? "congested" : "unknown",
    };
  });
}
export function recommendationTargets(result: Recommendation | null): RouteTarget[] {
  if (!result) return [];
  const places = [...result.places, ...result.areas];
  const targets = new Map<string, RouteTarget>();
  for (const objective of objectives) {
    const name = result.objectives[objective].plan?.target_location;
    const place = places.find((p) => p.name === name && Number.isFinite(p.lat) && Number.isFinite(p.lng));
    if (!place) continue;
    const key = `${place.lat}:${place.lng}`;
    const existing = targets.get(key);
    if (existing) existing.objectives.push(objective);
    else targets.set(key, { place, objectives: [objective] });
  }
  return [...targets.values()];
}
const cache = new Map<string, { expires: number; promise: Promise<RoadRoute> }>();
export function roadRoute(lat: number, lng: number, place: Place): Promise<RoadRoute> {
  const params = new URLSearchParams({
    origin_lat: String(lat),
    origin_lon: String(lng),
    destination_lat: String(place.lat),
    destination_lon: String(place.lng),
  });
  const key = params.toString();
  const entry = cache.get(key);
  if (entry && entry.expires > Date.now()) return entry.promise;
  const promise = api<{ route: RoadRoute }>(`/api/route?${params}`)
    .then((data) => {
      const points = data.route?.legs?.flatMap((leg) => leg.points) ?? [];
      if (points.length < 2 || points.some((p) => !Number.isFinite(p.latitude) || !Number.isFinite(p.longitude)))
        throw new Error("Không có hình tuyến đường hợp lệ.");
      return data.route;
    })
    .catch((error) => {
      cache.delete(key);
      throw error;
    });
  if (cache.size >= 32) cache.delete(cache.keys().next().value!);
  cache.set(key, { expires: Date.now() + 60000, promise });
  return promise;
}

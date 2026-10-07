import type { MetadataRoute } from "next";
const SITE_URL = process.env.GIGCA_SITE_URL || "http://localhost:3000";
export default function sitemap(): MetadataRoute.Sitemap {
  return ["/dashboard/gigca", "/dashboard/gigca/map", "/dashboard/gigca/conditions", "/dashboard/gigca/sources"].map((route) => ({url: `${SITE_URL}${route}`}));
}

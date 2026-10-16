import packageJson from "../../package.json";

const currentYear = new Date().getFullYear();

export const APP_CONFIG = {
  name: "GigCa",
  version: packageJson.version,
  copyright: `© ${currentYear}, GigCa.`,
  meta: {
    title: "GigCa · Gợi ý cho tài xế",
    description:
      "Điểm chờ, lộ trình, thời tiết và giao thông cho tài xế.",
  },
};

const SITE_LABELS: Record<string, string> = {
  dubai: "Dubai",
  riyadh: "Riyadh",
  abu_dhabi: "Abu Dhabi",
  doha: "Doha",
  kuwait_city: "Kuwait City",
  muscat: "Muscat",
  manama: "Manama",
};

export function prettySiteKey(key: string): string {
  return (
    SITE_LABELS[key] ??
    key.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase())
  );
}

export const DEMO_SITE_KEYS = new Set(["dubai", "riyadh", "abu_dhabi", "doha"]);

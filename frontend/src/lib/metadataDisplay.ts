const MAX_DISPLAY_SUBJECTS = 6;

const GENERIC_SUBJECTS = new Set([
  "adult",
  "book",
  "books",
  "contemporary",
  "fiction",
  "general",
  "juvenile fiction",
  "language arts disciplines",
  "literature",
  "nonfiction",
  "novel",
  "novels",
  "text"
]);

const JUNK_PHRASES = [
  "accessible book",
  "bibliography",
  "catalog record",
  "electronic book",
  "examinations",
  "grade level",
  "imported from",
  "internet archive",
  "large print",
  "large type",
  "library catalog",
  "machine generated",
  "open library list",
  "protected daisy",
  "reading level",
  "study guide",
  "subject headings",
  "textbook",
  "translations",
  "works by one author"
];

const SUBJECT_VARIANTS: Record<string, string> = {
  "ciencia ficcion": "Science Fiction",
  "dystopian fiction": "Dystopian",
  dystopias: "Dystopian",
  dystopie: "Dystopian",
  dystopies: "Dystopian",
  "fantasy fiction": "Fantasy",
  fantastique: "Fantasy",
  "ficcion historica": "Historical Fiction",
  "fiction historique": "Historical Fiction",
  "fiction scientifique": "Science Fiction",
  "historias de amor": "Romance",
  "historical fiction": "Historical Fiction",
  "juvenile literature": "Young Adult",
  "love stories": "Romance",
  "love story": "Romance",
  "romance fiction": "Romance",
  "science fiction": "Science Fiction",
  "young adult fiction": "Young Adult"
};

const LANGUAGE_NAMES: Record<string, string> = {
  ar: "Arabic", ara: "Arabic",
  ca: "Catalan", cat: "Catalan",
  zh: "Chinese", chi: "Chinese", zho: "Chinese",
  cs: "Czech", ces: "Czech", cze: "Czech",
  da: "Danish", dan: "Danish",
  nl: "Dutch", dut: "Dutch", nld: "Dutch",
  en: "English", eng: "English", english: "English",
  fi: "Finnish", fin: "Finnish",
  fr: "French", fra: "French", fre: "French", french: "French",
  de: "German", deu: "German", ger: "German", german: "German",
  el: "Greek", ell: "Greek", gre: "Greek",
  he: "Hebrew", heb: "Hebrew",
  hi: "Hindi", hin: "Hindi",
  id: "Indonesian", ind: "Indonesian",
  it: "Italian", ita: "Italian",
  ja: "Japanese", jpn: "Japanese",
  ko: "Korean", kor: "Korean",
  la: "Latin", lat: "Latin",
  no: "Norwegian", nor: "Norwegian",
  pl: "Polish", pol: "Polish",
  pt: "Portuguese", por: "Portuguese",
  ru: "Russian", rus: "Russian",
  es: "Spanish", spa: "Spanish", spanish: "Spanish",
  sv: "Swedish", swe: "Swedish",
  th: "Thai", tha: "Thai",
  tr: "Turkish", tur: "Turkish",
  vi: "Vietnamese", vie: "Vietnamese", vietnamese: "Vietnamese"
};

function normalizedKey(value: string): string {
  return value
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, " ")
    .trim()
    .replace(/\s+/g, " ");
}

function titleCase(value: string): string {
  const smallWords = new Set(["and", "for", "in", "of", "on", "the", "to", "with"]);
  return value
    .split(" ")
    .map((word, index) =>
      index > 0 && smallWords.has(word) ? word : `${word.charAt(0).toUpperCase()}${word.slice(1)}`
    )
    .join(" ");
}

function isNoise(value: string): boolean {
  if (!value || value.length < 2 || value.length > 60 || value.split(" ").length > 7) return true;
  if (GENERIC_SUBJECTS.has(value)) return true;
  if (/^\d+$/.test(value)) return true;
  if (/^(?:isbn|oclc|lccn|ddc|lcsh|openlibrary|goodreads|list)\b/.test(value)) return true;
  if (/^[a-z][a-z0-9_-]{1,24}:[^\s]+$/.test(value)) return true;
  return JUNK_PHRASES.some((phrase) => value.includes(phrase));
}

export function cleanDisplaySubjects(subjects: string[] = [], genres: string[] = []): string[] {
  const genreKeys = new Set(genres.map(normalizedKey));
  const seen = new Set<string>();
  const candidates: Array<{ label: string; priority: number; index: number }> = [];

  subjects.forEach((subject, index) => {
    const key = normalizedKey(subject);
    if (isNoise(key)) return;
    const label = SUBJECT_VARIANTS[key] ?? titleCase(key);
    const displayKey = normalizedKey(label);
    if (genreKeys.has(displayKey) || seen.has(displayKey)) return;
    seen.add(displayKey);
    candidates.push({
      label,
      priority: SUBJECT_VARIANTS[key] ? 0 : 1,
      index
    });
  });

  return candidates
    .sort((a, b) => a.priority - b.priority || a.index - b.index)
    .slice(0, MAX_DISPLAY_SUBJECTS)
    .map((candidate) => candidate.label);
}

export function displayLanguageName(value: string | null | undefined): string {
  const key = normalizedKey(value ?? "");
  if (!key || key === "und" || key === "unknown" || key === "mul") return "Unknown";
  if (LANGUAGE_NAMES[key]) return LANGUAGE_NAMES[key];
  return Object.values(LANGUAGE_NAMES).find((name) => normalizedKey(name) === key) ?? "Unknown";
}

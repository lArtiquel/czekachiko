import type { Option } from '../api/types';

/** Prefixes people type: Polish without diacritics, Russian, capitals. From czekachiko/share.py. */
const ALIASES: Record<string, readonly string[]> = {
  dolnoslaskie: ['dolno', 'нижнесилез', 'wroclaw', 'вроцлав'],
  kujawsko_pomorskie: ['kujaw', 'куяв', 'bydgoszcz', 'быдгощ', 'torun', 'торун'],
  lubelskie: ['lubel', 'lublin', 'люблин'],
  lubuskie: ['lubus', 'любуш', 'zielona', 'зелена', 'gorzow', 'гожув'],
  lodzkie: ['lodz', 'лодз'],
  malopolskie: ['malopol', 'малопол', 'krakow', 'краков'],
  mazowieckie: ['mazow', 'мазов', 'warszaw', 'варшав', 'warsaw'],
  opolskie: ['opol', 'опол'],
  podkarpackie: ['podkarpac', 'подкарпат', 'rzeszow', 'жешув'],
  podlaskie: ['podlas', 'подляш', 'bialystok', 'белосток'],
  pomorskie: ['pomorsk', 'поморск', 'gdansk', 'гданьск', 'gdynia', 'гдын'],
  slaskie: ['slask', 'силез', 'katowic', 'катовиц'],
  swietokrzyskie: ['swieto', 'свентокш', 'kielce', 'кельц'],
  warminsko_mazurskie: ['warmin', 'варми', 'olsztyn', 'ольштын'],
  wielkopolskie: ['wielkopol', 'великопол', 'poznan', 'познан'],
  zachodniopomorskie: ['zachodnio', 'западнопомор', 'szczecin', 'щецин'],
};

export function normalize(text: string): string {
  return text
    .toLowerCase()
    .replace(/ł/g, 'l')
    .normalize('NFKD')
    .replace(/[̀-ͯ]/g, '')
    .trim();
}

export function filterVoivodeships(options: Option[], query: string): Option[] {
  const q = normalize(query);
  if (!q) return options;
  return options.filter((o) => {
    if (normalize(o.label).includes(q)) return true;
    return (ALIASES[o.code] ?? []).some((a) => a.startsWith(q) || (q.length >= 3 && q.startsWith(a)));
  });
}

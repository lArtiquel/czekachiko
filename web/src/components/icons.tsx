/** A small stroke icon set on a 24px grid. Decorative: always aria-hidden. */
const PATHS = {
  chevronRight: ['M9.5 6l6 6-6 6'],
  chevronDown: ['M6 9.5l6 6 6-6'],
  plus: ['M12 5v14', 'M5 12h14'],
  close: ['M7 7l10 10', 'M17 7L7 17'],
  check: ['M5.5 12.5l4 4 9-9'],
  calendar: ['M6.5 5h11A2.5 2.5 0 0 1 20 7.5v10a2.5 2.5 0 0 1-2.5 2.5h-11A2.5 2.5 0 0 1 4 17.5v-10A2.5 2.5 0 0 1 6.5 5z', 'M4 10h16', 'M8.5 3v4', 'M15.5 3v4'],
  chart: ['M5 20V12', 'M12 20V5', 'M19 20v-5'],
  sliders: ['M4 7.5h9', 'M19 7.5h1', 'M4 16.5h3', 'M13 16.5h7', 'M16 5a2.5 2.5 0 1 1 0 5 2.5 2.5 0 0 1 0-5z', 'M10 14a2.5 2.5 0 1 1 0 5 2.5 2.5 0 0 1 0-5z'],
  mail: ['M5.5 5h13A2.5 2.5 0 0 1 21 7.5v9a2.5 2.5 0 0 1-2.5 2.5h-13A2.5 2.5 0 0 1 3 16.5v-9A2.5 2.5 0 0 1 5.5 5z', 'M4 7l8 6 8-6'],
  share: ['M17.5 3a2.5 2.5 0 1 1 0 5 2.5 2.5 0 0 1 0-5z', 'M6.5 9.5a2.5 2.5 0 1 1 0 5 2.5 2.5 0 0 1 0-5z', 'M17.5 16a2.5 2.5 0 1 1 0 5 2.5 2.5 0 0 1 0-5z', 'M8.7 10.8l6.6-3.6', 'M8.7 13.2l6.6 3.6'],
  send: ['M20.5 3.5L10 14', 'M20.5 3.5l-6 17-4.5-6.5-6.5-4.5 17-6z'],
  trash: ['M4.5 7h15', 'M9.5 7V4.5h5V7', 'M6.5 7l.9 11.6A2.5 2.5 0 0 0 9.9 21h4.2a2.5 2.5 0 0 0 2.5-2.4L17.5 7', 'M10 11v6', 'M14 11v6'],
  clock: ['M12 3a9 9 0 1 1 0 18 9 9 0 0 1 0-18z', 'M12 7.5V12l3 2'],
  doc: ['M7 3h6.5L19 8.5V18.5a2.5 2.5 0 0 1-2.5 2.5h-9.5A2.5 2.5 0 0 1 4.5 18.5v-13A2.5 2.5 0 0 1 7 3z', 'M13.5 3v5.5H19', 'M8.5 13h7', 'M8.5 16.5h4.5'],
  info: ['M12 3a9 9 0 1 1 0 18 9 9 0 0 1 0-18z', 'M12 11v5.5', 'M12 7.75v.01'],
  external: ['M13.5 4.5h6v6', 'M19.5 4.5L11 13', 'M18 14v3.5a2.5 2.5 0 0 1-2.5 2.5h-9A2.5 2.5 0 0 1 4 17.5v-9A2.5 2.5 0 0 1 6.5 6H10'],
  search: ['M10.5 4a6.5 6.5 0 1 1 0 13 6.5 6.5 0 0 1 0-13z', 'M20 20l-4.8-4.8'],
  refresh: ['M19.5 12a7.5 7.5 0 1 1-2.2-5.3', 'M19.5 4v4.5H15'],
  globe: ['M12 3a9 9 0 1 1 0 18 9 9 0 0 1 0-18z', 'M3 12h18', 'M12 3c2.4 2.5 3.6 5.5 3.6 9s-1.2 6.5-3.6 9c-2.4-2.5-3.6-5.5-3.6-9S9.6 5.5 12 3z'],
  lock: ['M6.5 10.5h11a1.5 1.5 0 0 1 1.5 1.5v6.5a2.5 2.5 0 0 1-2.5 2.5h-9A2.5 2.5 0 0 1 5 18.5V12a1.5 1.5 0 0 1 1.5-1.5z', 'M8 10.5V8a4 4 0 0 1 8 0v2.5'],
  help: ['M12 3a9 9 0 1 1 0 18 9 9 0 0 1 0-18z', 'M9.6 9.4a2.5 2.5 0 1 1 3.6 2.3c-.7.3-1.2.9-1.2 1.7v.4', 'M12 17v.01'],
  pencil: ['M4.5 19.5h4l10-10a2.8 2.8 0 0 0-4-4l-10 10v4z', 'M13 7l4 4'],
} as const;

export type IconName = keyof typeof PATHS;

export function Icon({ name, size = 20, className }: { name: IconName; size?: number; className?: string }) {
  return (
    <svg
      className={className ? `icon ${className}` : 'icon'}
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.9}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      {PATHS[name].map((d) => (
        <path key={d} d={d} />
      ))}
    </svg>
  );
}

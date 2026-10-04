/** Small stroke icons for the dashboard (currentColor, 24×24 grid). */

const PATHS: Record<string, string> = {
  sunrise: "M3 18h18M6 14a6 6 0 0 1 12 0M12 3v4M4.2 7.2l2.1 2.1M19.8 7.2l-2.1 2.1M8 21h8",
  target: "M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18zM12 7a5 5 0 1 0 0 10 5 5 0 0 0 0-10zM12 11a1 1 0 1 0 0 2 1 1 0 0 0 0-2z",
  bulb: "M9 18h6M10 21h4M12 3a6 6 0 0 0-3.5 10.9c.6.5 1 1.2 1 2.1h5c0-.9.4-1.6 1-2.1A6 6 0 0 0 12 3z",
  loop: "M4 12a8 8 0 0 1 14-5.3L20 9M20 4v5h-5M20 12a8 8 0 0 1-14 5.3L4 15M4 20v-5h5",
  rocket: "M5 15c-1.5 1.5-2 5-2 5s3.5-.5 5-2M9 12l3 3M14.5 4.5C17 3 20.5 3 20.5 3s0 3.5-1.5 6l-6 6-4-4 6-6.5zM15 9a1 1 0 1 0 0-.01",
  pen: "M4 20l4-1L19 8l-3-3L5 16l-1 4zM14 7l3 3",
  flame: "M12 21c-3.9 0-7-2.7-7-6.5 0-3 2-5 3.5-6.5.3 1.6 1.2 2.8 2.5 3.5C11 8 12 5 15 3c-.3 2.7 1 4.6 2.5 6.3 1 1.2 1.5 2.7 1.5 4.2 0 4.2-3 7.5-7 7.5z",
  flag: "M5 21V4M5 4h11l-2 4 2 4H5",
  bolt: "M13 2L4 14h7l-1 8 9-12h-7l1-8z",
  clock: "M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18zM12 7v5l3 2",
  check: "M5 12.5l4.5 4.5L19 7.5",
  dot: "M12 10a2 2 0 1 0 0 4 2 2 0 0 0 0-4z",
  alert: "M12 8v5M12 16.5v.5M10.3 3.9L2.4 18a2 2 0 0 0 1.7 3h15.8a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z",
  half: "M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18zM12 3v18",
  printer: "M7 9V3h10v6M7 18H5a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2M7 14h10v7H7z",
  hourglass: "M6 3h12M6 21h12M7 3c0 4 5 5 5 9s-5 5-5 9M17 3c0 4-5 5-5 9s5 5 5 9",
};

export function Icon({ name, className, title }: { name: string; className?: string; title?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.8}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      role={title ? "img" : undefined}
      aria-hidden={title ? undefined : true}
      aria-label={title}
    >
      <path d={PATHS[name] ?? PATHS.dot} />
    </svg>
  );
}

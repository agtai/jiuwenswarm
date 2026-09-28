import type { SVGProps } from 'react';

// A chalkboard on an easel with a line of handwriting, drawn like the app's other 16px rail icons.
export function BlackboardIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg
      viewBox="0 0 16 16"
      fill="none"
      stroke="currentColor"
      strokeWidth={1}
      strokeLinecap="round"
      strokeLinejoin="round"
      {...props}
    >
      <rect x="1.5" y="2" width="13" height="9.5" rx="1" />
      <path d="M3.75 8.25c.7-1.4 1.2-2.6 1.8-2.6.7 0 .1 2.6.9 2.6.7 0 1-1.9 1.8-1.9.6 0 .5 1.5 1.3 1.5.6 0 1-.8 1.5-1.4.3-.3.6-.3.9 0" />
      <path d="M4.5 14.5l1-3M11.5 14.5l-1-3" />
    </svg>
  );
}

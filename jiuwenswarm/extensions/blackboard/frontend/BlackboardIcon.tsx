import type { SVGProps } from 'react';

// A blank chalkboard on an easel, with a stick of chalk on its ledge, drawn like the app's other
// 16px rail icons.
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
      <path d="M9.5 9.5h2.5" />
      <path d="M4.5 14.5l1-3M11.5 14.5l-1-3" />
    </svg>
  );
}

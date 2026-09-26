import type { SVGProps } from "react";

type IconProps = SVGProps<SVGSVGElement>;

function iconProps({ className, ...rest }: IconProps): SVGProps<SVGSVGElement> {
  return {
    xmlns: "http://www.w3.org/2000/svg",
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 1.6,
    strokeLinecap: "round",
    strokeLinejoin: "round",
    "aria-hidden": true,
    focusable: false,
    className: className ?? "h-4 w-4",
    ...rest,
  };
}

export function CheckIcon(props: IconProps) {
  return (
    <svg {...iconProps(props)}>
      <path d="M4.5 12.5l4.5 4.5 10-10" />
    </svg>
  );
}

export function ChevronIcon(props: IconProps) {
  return (
    <svg {...iconProps(props)}>
      <path d="M6 9l6 6 6-6" />
    </svg>
  );
}

export function UploadCloudIcon(props: IconProps) {
  return (
    <svg {...iconProps(props)}>
      <path d="M7 17.5A4.5 4.5 0 0 1 7.4 8.6a5.5 5.5 0 0 1 10.5 1.6A3.9 3.9 0 0 1 17.5 17.5Z" />
      <path d="M12 12v7" />
      <path d="M9.5 14.5L12 12l2.5 2.5" />
    </svg>
  );
}

export function ImageIcon(props: IconProps) {
  return (
    <svg {...iconProps(props)}>
      <rect x="3" y="4" width="18" height="16" rx="2.5" />
      <circle cx="8.5" cy="9.5" r="1.6" />
      <path d="M3.5 17l4.8-4.4a2 2 0 0 1 2.7 0L21 21" />
    </svg>
  );
}

export function TrashIcon(props: IconProps) {
  return (
    <svg {...iconProps(props)}>
      <path d="M4 7h16" />
      <path d="M9.5 7V5.5A1.5 1.5 0 0 1 11 4h2a1.5 1.5 0 0 1 1.5 1.5V7" />
      <path d="M6.5 7l.8 12.1A2 2 0 0 0 9.3 21h5.4a2 2 0 0 0 2-1.9L17.5 7" />
    </svg>
  );
}

export function CloseIcon(props: IconProps) {
  return (
    <svg {...iconProps(props)}>
      <path d="M6 6l12 12" />
      <path d="M18 6L6 18" />
    </svg>
  );
}

export function PlayIcon(props: IconProps) {
  return (
    <svg {...iconProps(props)}>
      <path d="M8 5.5l10 6.5-10 6.5z" />
    </svg>
  );
}

export function ReplayIcon(props: IconProps) {
  return (
    <svg {...iconProps(props)}>
      <path d="M20 12a8 8 0 1 1-2.6-5.9" />
      <path d="M20 4v4.5h-4.5" />
    </svg>
  );
}

export function SearchIcon(props: IconProps) {
  return (
    <svg {...iconProps(props)}>
      <circle cx="11" cy="11" r="6.5" />
      <path d="M20 20l-4.3-4.3" />
    </svg>
  );
}

export function PinIcon(props: IconProps) {
  return (
    <svg {...iconProps(props)}>
      <path d="M12 21s7-5.6 7-11a7 7 0 1 0-14 0c0 5.4 7 11 7 11Z" />
      <circle cx="12" cy="10" r="2.6" />
    </svg>
  );
}

export function AlertIcon(props: IconProps) {
  return (
    <svg {...iconProps(props)}>
      <path d="M12 4.5 2.8 20h18.4L12 4.5Z" />
      <path d="M12 10v4.2" />
      <path d="M12 17.2h.01" />
    </svg>
  );
}

export function SpinnerIcon(props: IconProps) {
  return (
    <svg {...iconProps({ className: "animate-spin", ...props })}>
      <path d="M12 3a9 9 0 1 0 9 9" />
    </svg>
  );
}

export function LayersIcon(props: IconProps) {
  return (
    <svg {...iconProps(props)}>
      <path d="M12 3.5 3 8l9 4.5L21 8l-9-4.5Z" />
      <path d="M3 13.5 12 18l9-4.5" />
    </svg>
  );
}

export function SatelliteIcon(props: IconProps) {  return (
    <svg {...iconProps(props)}>
      <circle cx="12" cy="12" r="2.5" />
      <path d="M7.2 10.2 3.5 8.5l2-2.5 3.6 1.4" />
      <path d="M16.8 13.8l3.7 1.7-2 2.5-3.6-1.4" />
      <path d="M10.2 7.2 8.5 3.5 11 1.5l1.4 3.6" />
      <path d="M13.8 16.8l1.7 3.7-2.5 2-1.4-3.6" />
    </svg>
  );
}

export function OrbitGlyph(props: IconProps) {
  return (
    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" {...props}>
      <circle cx="8" cy="8" r="3" />
      <ellipse cx="8" cy="8" rx="7" ry="3" transform="rotate(-20 8 8)" />
    </svg>
  );
}

export function ZoomInIcon(props: IconProps) {
  return (
    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" {...props}>
      <circle cx="7" cy="7" r="4.2" />
      <path d="M10.2 10.2 14 14M7 5.2v3.6M5.2 7h3.6" />
    </svg>
  );
}

export function ZoomOutIcon(props: IconProps) {
  return (
    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" {...props}>
      <circle cx="7" cy="7" r="4.2" />
      <path d="M10.2 10.2 14 14M5.2 7h3.6" />
    </svg>
  );
}

export function CrosshairIcon(props: IconProps) {
  return (
    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" {...props}>
      <path d="M8 1.5v3M8 11.5v3M1.5 8h3M11.5 8h3" />
      <circle cx="8" cy="8" r="2.6" />
    </svg>
  );
}
const GREYS = ["#111111", "#2a2a2a", "#444444", "#5c5c5c", "#767676", "#8f8f8f"];

function ring(count: number, radius: number, sizeRange: [number, number], seedOffset = 0) {
  return Array.from({ length: count }, (_, i) => {
    const angle = (i / count) * Math.PI * 2 + seedOffset;
    const x = 16 + radius * Math.cos(angle);
    const y = 16 + radius * Math.sin(angle);
    const t = (i * 37) % 100 / 100;
    const size = sizeRange[0] + t * (sizeRange[1] - sizeRange[0]);
    const color = GREYS[i % GREYS.length];
    const opacity = 0.6 + 0.4 * ((i * 17) % 100) / 100;
    return { x, y, size, color, opacity };
  });
}

export default function Logo({ size = 28 }: { size?: number }) {
  const rings = [
    ...ring(6, 3.5, [1, 1.6], 0.1),
    ...ring(10, 6.5, [0.9, 1.7], 0.3),
    ...ring(14, 9.5, [0.8, 1.8], 0.5),
    ...ring(18, 12.5, [0.7, 1.6], 0.15),
    ...ring(20, 15, [0.5, 1.2], 0.4),
  ];

  return (
    <svg width={size} height={size} viewBox="0 0 32 32" fill="none" aria-hidden="true">
      {rings.map((d, i) => (
        <circle key={i} cx={d.x} cy={d.y} r={d.size} fill={d.color} opacity={d.opacity} />
      ))}
      <circle cx="16" cy="16" r="2.6" fill="#111111" />
    </svg>
  );
}
"use client";

import { useId, useMemo, useState } from "react";

export interface SparkPoint {
  label: string;
  value: number;
}

/**
 * Single-series time trend.
 *
 * Design decisions, deliberately:
 *  - ONE series, so there is no legend and no categorical palette: the heading names it.
 *    Colour is the app's single accent hue, never a cycled series colour.
 *  - One y-axis only, and it starts at zero so bar/area height stays proportional.
 *  - Direct labels are selective (peak and latest only), not a number on every point.
 *  - Grid and axis are recessive; the data is the darkest thing in the frame.
 *  - Hover gives a crosshair + tooltip, and a table view is always available underneath,
 *    so the value is never locked behind a pointer (or behind colour vision).
 */
export function Sparkline({
  points,
  height = 160,
  valueFormatter = (value: number) => value.toLocaleString()
}: {
  points: SparkPoint[];
  height?: number;
  valueFormatter?: (value: number) => string;
}) {
  const gradientId = useId().replace(/:/g, "");
  const [hover, setHover] = useState<number | null>(null);

  const geometry = useMemo(() => {
    const width = 720;
    const padding = { top: 16, right: 16, bottom: 26, left: 44 };
    const plotWidth = width - padding.left - padding.right;
    const plotHeight = height - padding.top - padding.bottom;
    const maxValue = Math.max(1, ...points.map((point) => point.value));
    const step = points.length > 1 ? plotWidth / (points.length - 1) : plotWidth;

    const coords = points.map((point, index) => ({
      ...point,
      x: padding.left + index * step,
      y: padding.top + plotHeight - (point.value / maxValue) * plotHeight
    }));

    return { width, padding, plotWidth, plotHeight, maxValue, coords, step };
  }, [points, height]);

  if (points.length === 0) {
    return <p className="muted small">No data in this window yet.</p>;
  }

  const { width, padding, plotHeight, maxValue, coords } = geometry;
  const line = coords.map((point, index) => `${index === 0 ? "M" : "L"}${point.x.toFixed(1)},${point.y.toFixed(1)}`).join(" ");
  const area = `${line} L${coords[coords.length - 1].x.toFixed(1)},${(padding.top + plotHeight).toFixed(1)} L${coords[0].x.toFixed(1)},${(padding.top + plotHeight).toFixed(1)} Z`;

  const peakIndex = coords.reduce((best, point, index) => (point.value > coords[best].value ? index : best), 0);
  const lastIndex = coords.length - 1;
  const labelled = new Set([peakIndex, lastIndex]);
  const active = hover !== null ? coords[hover] : null;
  const total = points.reduce((sum, point) => sum + point.value, 0);

  return (
    <div className="chart">
      <svg
        viewBox={`0 0 ${width} ${height}`}
        className="chart-svg"
        role="img"
        aria-label={`Trend over ${points.length} days. Total ${valueFormatter(total)}. Peak ${valueFormatter(coords[peakIndex].value)} on ${coords[peakIndex].label}.`}
        onMouseLeave={() => setHover(null)}
        onMouseMove={(event) => {
          const box = event.currentTarget.getBoundingClientRect();
          const ratio = (event.clientX - box.left) / box.width;
          const x = ratio * width;
          let nearest = 0;
          coords.forEach((point, index) => {
            if (Math.abs(point.x - x) < Math.abs(coords[nearest].x - x)) nearest = index;
          });
          setHover(nearest);
        }}
      >
        <defs>
          <linearGradient id={`spark-${gradientId}`} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="var(--primary)" stopOpacity="0.22" />
            <stop offset="100%" stopColor="var(--primary)" stopOpacity="0.02" />
          </linearGradient>
        </defs>

        {/* Recessive gridlines: three references, y starting at zero. */}
        {[0, 0.5, 1].map((fraction) => {
          const y = padding.top + plotHeight * fraction;
          return (
            <g key={fraction}>
              <line x1={padding.left} y1={y} x2={width - padding.right} y2={y} className="chart-grid" />
              <text x={padding.left - 8} y={y + 4} className="chart-axis-label" textAnchor="end">
                {valueFormatter(maxValue * (1 - fraction))}
              </text>
            </g>
          );
        })}

        <path d={area} fill={`url(#spark-${gradientId})`} />
        <path d={line} className="chart-line" />

        {active ? (
          <>
            <line x1={active.x} y1={padding.top} x2={active.x} y2={padding.top + plotHeight} className="chart-crosshair" />
            {/* 2px surface ring so the marker reads on top of the area fill. */}
            <circle cx={active.x} cy={active.y} r={6} className="chart-marker-ring" />
            <circle cx={active.x} cy={active.y} r={4} className="chart-marker" />
          </>
        ) : null}

        {[...labelled].map((index) => (
          <circle key={index} cx={coords[index].x} cy={coords[index].y} r={3.5} className="chart-marker" />
        ))}

        {/* First and last date only: enough to orient, no axis clutter. */}
        <text x={padding.left} y={height - 8} className="chart-axis-label">
          {new Date(points[0].label).toLocaleDateString(undefined, { month: "short", day: "numeric" })}
        </text>
        <text x={width - padding.right} y={height - 8} className="chart-axis-label" textAnchor="end">
          {new Date(points[lastIndex].label).toLocaleDateString(undefined, { month: "short", day: "numeric" })}
        </text>
      </svg>

      <div className="chart-caption">
        {active ? (
          <span>
            <strong>{new Date(active.label).toLocaleDateString()}</strong> · {valueFormatter(active.value)}
          </span>
        ) : (
          <span className="muted">
            Peak {valueFormatter(coords[peakIndex].value)} on {new Date(coords[peakIndex].label).toLocaleDateString()} · total{" "}
            {valueFormatter(total)}
          </span>
        )}
      </div>

      <details className="chart-table">
        <summary>View as table</summary>
        <table className="table">
          <thead>
            <tr>
              <th>Date</th>
              <th>Value</th>
            </tr>
          </thead>
          <tbody>
            {points.map((point) => (
              <tr key={point.label}>
                <td>{new Date(point.label).toLocaleDateString()}</td>
                <td>{valueFormatter(point.value)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </details>
    </div>
  );
}

// Scores describe the predicted class, not calibrated certainty of a switch event.
export function nextDirectionChange(rows, initialDirection) {
  let previous = ['07', '25'].includes(initialDirection) ? initialDirection : null;
  for (const row of rows) {
    if (!Number.isFinite(row.p07) || row.available === false) { previous = null; continue; }
    const direction = row.p07 >= 0.5 ? '07' : '25';
    if (previous && direction !== previous) return {
      time: row.time, from: previous, to: direction,
      directionScore: Math.max(row.p07, 1 - row.p07), resolutionHours: 1,
    };
    previous = direction;
  }
  return null;
}

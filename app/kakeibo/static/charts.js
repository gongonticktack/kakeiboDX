/* 外部通信なしで家計簿グラフを描く。 */
(() => {
  const palette = ["#ff7043", "#1f4b3f", "#f0b44d", "#6e8f7d", "#a55eea", "#3d8bfd", "#d65d7a", "#607d3b", "#805a46", "#9aa3a0"];
  const yen = value => `¥${Number(value).toLocaleString("ja-JP")}`;

  function donut(canvas, rows) {
    const ctx = canvas.getContext("2d");
    const ratio = window.devicePixelRatio || 1;
    const size = Math.min(canvas.clientWidth || 280, 280);
    canvas.width = size * ratio; canvas.height = size * ratio;
    ctx.scale(ratio, ratio);
    const total = rows.reduce((sum, row) => sum + Number(row.amount), 0);
    const center = size / 2;
    if (!total) {
      ctx.strokeStyle = "#e7e8e3"; ctx.lineWidth = 34;
      ctx.beginPath(); ctx.arc(center, center, size * .31, 0, Math.PI * 2); ctx.stroke();
      ctx.fillStyle = "#77807c"; ctx.textAlign = "center"; ctx.font = "14px sans-serif";
      ctx.fillText("データなし", center, center + 5); return;
    }
    let angle = -Math.PI / 2;
    rows.forEach((row, index) => {
      const next = angle + (Number(row.amount) / total) * Math.PI * 2;
      ctx.beginPath(); ctx.strokeStyle = palette[index % palette.length]; ctx.lineWidth = 36;
      ctx.arc(center, center, size * .31, angle + .01, next - .01); ctx.stroke(); angle = next;
    });
    ctx.fillStyle = "#17231f"; ctx.textAlign = "center"; ctx.font = "700 21px sans-serif";
    ctx.fillText(yen(total), center, center + 4);
    ctx.fillStyle = "#77807c"; ctx.font = "12px sans-serif"; ctx.fillText("合計", center, center - 22);
  }

  function legend(target, rows) {
    target.innerHTML = rows.map((row, index) => `
      <div class="legend-row"><i style="background:${palette[index % palette.length]}"></i>
      <span>${row.category}</span><b>${yen(row.amount)}</b></div>`).join("") || "<p class='muted'>データがありません</p>";
  }

  function bars(canvas, rows) {
    const ctx = canvas.getContext("2d");
    const ratio = window.devicePixelRatio || 1;
    const width = canvas.clientWidth || 640, height = 310;
    canvas.width = width * ratio; canvas.height = height * ratio; ctx.scale(ratio, ratio);
    const pad = {top: 24, right: 18, bottom: 44, left: 64};
    const max = Math.max(...rows.map(row => Number(row.amount)), 1);
    ctx.font = "11px sans-serif"; ctx.fillStyle = "#77807c"; ctx.textAlign = "right";
    for (let i = 0; i <= 4; i++) {
      const y = pad.top + (height - pad.top - pad.bottom) * i / 4;
      ctx.strokeStyle = "#e7e8e3"; ctx.beginPath(); ctx.moveTo(pad.left, y); ctx.lineTo(width - pad.right, y); ctx.stroke();
      ctx.fillText(yen(Math.round(max * (4 - i) / 4)), pad.left - 8, y + 4);
    }
    if (!rows.length) return;
    const area = width - pad.left - pad.right;
    const step = area / rows.length;
    rows.forEach((row, index) => {
      const barHeight = Number(row.amount) / max * (height - pad.top - pad.bottom);
      const x = pad.left + index * step + step * .18;
      ctx.fillStyle = "#ff7043"; ctx.beginPath();
      ctx.roundRect(x, height - pad.bottom - barHeight, step * .64, barHeight, 5); ctx.fill();
      ctx.fillStyle = "#66706c"; ctx.textAlign = "center";
      ctx.fillText(row.month, x + step * .32, height - 18);
    });
  }

  const data = window.KAKEIBO_DATA;
  donut(document.getElementById("categoryChart"), data.categories);
  legend(document.getElementById("categoryLegend"), data.categories);
  bars(document.getElementById("monthlyChart"), data.monthly);
})();


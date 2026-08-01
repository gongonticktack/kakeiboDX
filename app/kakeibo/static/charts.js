/* 外部通信なしで家計簿グラフを描く。 */
(() => {
  const fallbackColors = ["#65f5cf", "#c3a07a", "#f6d77b", "#35d6a9", "#75d7ff", "#9bf28f", "#8fc7ff", "#b2f7d0", "#ff9fc7", "#a9b5ad"];
  const yen = value => `¥${Number(value).toLocaleString("ja-JP")}`;
  const hitAreas = new WeakMap();
  const data = window.KAKEIBO_DATA;

  function categoryColor(row, index = 0) {
    return data.categoryColors?.[row.category] || fallbackColors[index % fallbackColors.length];
  }

  function moveTo(params) {
    const url = new URL(window.location.href);
    Object.entries(params).forEach(([key, value]) => {
      if (value) url.searchParams.set(key, value);
      else url.searchParams.delete(key);
    });
    window.location.href = url.toString();
  }

  function canvasPoint(canvas, event) {
    const rect = canvas.getBoundingClientRect();
    return {
      x: event.clientX - rect.left,
      y: event.clientY - rect.top,
    };
  }

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
    const areas = [];
    rows.forEach((row, index) => {
      const next = angle + (Number(row.amount) / total) * Math.PI * 2;
      ctx.beginPath(); ctx.strokeStyle = categoryColor(row, index); ctx.lineWidth = 36;
      ctx.arc(center, center, size * .31, angle + .01, next - .01); ctx.stroke();
      areas.push({type: "donut", start: angle, end: next, inner: size * .31 - 22, outer: size * .31 + 22, row});
      angle = next;
    });
    hitAreas.set(canvas, areas);
    ctx.fillStyle = "#f5fff9"; ctx.textAlign = "center"; ctx.font = "700 21px sans-serif";
    ctx.fillText(yen(total), center, center + 4);
    ctx.fillStyle = "#9cb7ad"; ctx.font = "12px sans-serif"; ctx.fillText("合計", center, center - 22);
  }

  function legend(target, rows) {
    target.innerHTML = rows.map((row, index) => `
      <div class="legend-row"><i style="background:${categoryColor(row, index)}"></i>
      <span>${row.category}</span><b>${yen(row.amount)}</b></div>`).join("") || "<p class='muted'>データがありません</p>";
    [...target.querySelectorAll(".legend-row")].forEach((element, index) => {
      element.style.cursor = "pointer";
      element.addEventListener("click", () => moveTo({category: rows[index].category}));
    });
  }

  function bars(canvas, rows) {
    const ctx = canvas.getContext("2d");
    const ratio = window.devicePixelRatio || 1;
    const width = canvas.clientWidth || 640, height = 310;
    canvas.width = width * ratio; canvas.height = height * ratio; ctx.scale(ratio, ratio);
    const pad = {top: 24, right: 18, bottom: 48, left: 64};
    const max = Math.max(...rows.map(row => Number(row.amount)), 1);
    ctx.font = "11px sans-serif"; ctx.fillStyle = "#9cb7ad"; ctx.textAlign = "right";
    for (let i = 0; i <= 4; i++) {
      const y = pad.top + (height - pad.top - pad.bottom) * i / 4;
      ctx.strokeStyle = "#244039"; ctx.beginPath(); ctx.moveTo(pad.left, y); ctx.lineTo(width - pad.right, y); ctx.stroke();
      ctx.fillText(yen(Math.round(max * (4 - i) / 4)), pad.left - 8, y + 4);
    }
    if (!rows.length) return;
    const area = width - pad.left - pad.right;
    const step = area / rows.length;
    const labelEvery = Math.max(1, Math.ceil(rows.length / Math.max(1, Math.floor(area / 58))));
    const areas = [];
    rows.forEach((row, index) => {
      const barHeight = Number(row.amount) / max * (height - pad.top - pad.bottom);
      const x = pad.left + index * step + step * .18;
      const barWidth = step * .64;
      const y = height - pad.bottom - barHeight;
      ctx.fillStyle = "#65f5cf"; ctx.beginPath();
      ctx.roundRect(x, y, barWidth, barHeight, 5); ctx.fill();
      areas.push({type: "bar", x, y, width: barWidth, height: barHeight, row});
      if (index % labelEvery === 0 || index === rows.length - 1) {
        ctx.fillStyle = "#9cb7ad"; ctx.textAlign = "center"; ctx.font = "10px sans-serif";
        ctx.fillText(row.month, x + step * .32, height - 18);
      }
    });
    hitAreas.set(canvas, areas);
  }

  function attachClicks(canvas) {
    canvas.addEventListener("click", event => {
      const point = canvasPoint(canvas, event);
      const areas = hitAreas.get(canvas) || [];
      for (const area of areas) {
        if (area.type === "bar") {
          const inside = point.x >= area.x && point.x <= area.x + area.width
            && point.y >= area.y && point.y <= area.y + area.height;
          if (inside) {
            moveTo({period: "month", value: area.row.month, category: ""});
            return;
          }
        }
        if (area.type === "donut") {
          const size = Math.min(canvas.clientWidth || 280, 280);
          const dx = point.x - size / 2;
          const dy = point.y - size / 2;
          const distance = Math.hypot(dx, dy);
          let angle = Math.atan2(dy, dx);
          if (angle < -Math.PI / 2) angle += Math.PI * 2;
          if (distance >= area.inner && distance <= area.outer && angle >= area.start && angle <= area.end) {
            moveTo({category: area.row.category});
            return;
          }
        }
      }
    });
  }

  function averageBars(canvas, rows) {
    if (!canvas || !rows.length) return;
    const ctx = canvas.getContext("2d");
    const ratio = window.devicePixelRatio || 1;
    const width = canvas.clientWidth || 840, height = 360;
    canvas.width = width * ratio; canvas.height = height * ratio; ctx.scale(ratio, ratio);
    const pad = {top: 18, right: 92, bottom: 24, left: 112};
    const rowHeight = (height - pad.top - pad.bottom) / rows.length;
    const maxDiff = Math.max(...rows.map(row => Math.abs(Number(row.difference))), 1);
    const center = pad.left + (width - pad.left - pad.right) / 2;
    const scale = (width - pad.left - pad.right) / 2 / maxDiff;
    ctx.clearRect(0, 0, width, height);
    ctx.strokeStyle = "#244039";
    ctx.beginPath(); ctx.moveTo(center, pad.top); ctx.lineTo(center, height - pad.bottom); ctx.stroke();
    rows.forEach((row, index) => {
      const y = pad.top + index * rowHeight + rowHeight * .18;
      const barHeight = Math.max(12, rowHeight * .48);
      const diff = Number(row.difference);
      const barWidth = Math.abs(diff) * scale;
      const x = diff >= 0 ? center : center - barWidth;
      ctx.fillStyle = categoryColor(row, index);
      ctx.beginPath(); ctx.roundRect(x, y, Math.max(2, barWidth), barHeight, 5); ctx.fill();
      ctx.fillStyle = "#f5fff9"; ctx.textAlign = "right"; ctx.font = "12px sans-serif";
      ctx.fillText(row.category, pad.left - 10, y + barHeight - 2);
      ctx.textAlign = diff >= 0 ? "left" : "right";
      ctx.fillStyle = "#9cb7ad";
      ctx.fillText(`${diff >= 0 ? "+" : ""}${yen(diff)}`, diff >= 0 ? x + barWidth + 8 : x - 8, y + barHeight - 2);
    });
  }

  function averageModal(rows) {
    const modal = document.getElementById("averageModal");
    const openButton = document.getElementById("openAverageModal");
    const closeButton = document.getElementById("closeAverageModal");
    const canvas = document.getElementById("averageChart");
    if (!modal || !openButton || !closeButton) return;
    const open = () => {
      modal.hidden = false;
      averageBars(canvas, rows);
    };
    const close = () => { modal.hidden = true; };
    openButton.addEventListener("click", open);
    closeButton.addEventListener("click", close);
    modal.addEventListener("click", event => {
      if (event.target === modal) close();
    });
    document.addEventListener("keydown", event => {
      if (event.key === "Escape" && !modal.hidden) close();
    });
  }

  function simpleModal(modalId, openId, closeId) {
    const modal = document.getElementById(modalId);
    const openButton = document.getElementById(openId);
    const closeButton = document.getElementById(closeId);
    if (!modal || !openButton || !closeButton) return;
    const open = () => { modal.hidden = false; };
    const close = () => { modal.hidden = true; };
    openButton.addEventListener("click", open);
    closeButton.addEventListener("click", close);
    modal.addEventListener("click", event => {
      if (event.target === modal) close();
    });
    document.addEventListener("keydown", event => {
      if (event.key === "Escape" && !modal.hidden) close();
    });
  }

  const categoryChart = document.getElementById("categoryChart");
  const monthlyChart = document.getElementById("monthlyChart");
  donut(categoryChart, data.categories);
  legend(document.getElementById("categoryLegend"), data.categories);
  bars(monthlyChart, data.monthly);
  attachClicks(categoryChart);
  attachClicks(monthlyChart);
  averageModal(data.averageComparison || []);
  simpleModal("manualModal", "openManualModal", "closeManualModal");
})();

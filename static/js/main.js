document.addEventListener("DOMContentLoaded", () => {
  // Auto-dismiss flash messages after a few seconds.
  const flashWrap = document.getElementById("flash-messages");
  if (flashWrap) {
    setTimeout(() => {
      flashWrap.querySelectorAll(".flash-message").forEach((el) => {
        el.style.transition = "opacity 300ms ease, transform 300ms ease";
        el.style.opacity = "0";
        el.style.transform = "translateY(-4px)";
      });
      setTimeout(() => { flashWrap.style.display = "none"; }, 320);
    }, 4500);
  }

  // Rotate the little chevron on <details> disclosures (order history rows).
  document.querySelectorAll("details").forEach((d) => {
    const marker = d.querySelector(".disclosure-marker");
    if (!marker) return;
    d.addEventListener("toggle", () => {
      marker.style.transform = d.open ? "rotate(90deg)" : "rotate(0deg)";
    });
  });
});

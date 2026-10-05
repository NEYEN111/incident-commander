/* Progressive enhancement: native radio navigation still works without JavaScript. */
(() => {
  document.querySelectorAll(".accident-detail .tabs").forEach((container) => {
    const bar = container.querySelector(".tab-bar");
    const entries = Array.from(bar.querySelectorAll("label[for]")).map((label) => {
      const radio = container.querySelector(`#${label.htmlFor}`);
      const panel = container.querySelector(`#panel-${label.htmlFor.slice(4)}`);
      return { label, radio, panel };
    });
    if (!entries.length || entries.some(({ radio, panel }) => !radio || !panel)) return;

    bar.setAttribute("role", "tablist");
    entries.forEach((entry) => {
      const button = document.createElement("button");
      button.type = "button";
      button.id = `${entry.radio.id}-control`;
      button.textContent = entry.label.textContent;
      button.setAttribute("role", "tab");
      button.setAttribute("aria-controls", entry.panel.id);
      entry.panel.setAttribute("role", "tabpanel");
      entry.panel.setAttribute("aria-labelledby", button.id);
      entry.panel.tabIndex = 0;
      entry.radio.hidden = true;
      entry.label.replaceWith(button);
      entry.button = button;
    });

    const activate = (index, focus = false) => {
      entries.forEach(({ button, radio, panel }, current) => {
        const selected = current === index;
        button.setAttribute("aria-selected", String(selected));
        button.tabIndex = selected ? 0 : -1;
        radio.checked = selected;
        panel.hidden = !selected;
      });
      if (focus) entries[index].button.focus();
    };
    entries.forEach(({ button }, index) => {
      button.addEventListener("click", () => activate(index));
      button.addEventListener("keydown", (event) => {
        let next;
        if (event.key === "ArrowRight") next = (index + 1) % entries.length;
        else if (event.key === "ArrowLeft") next = (index + entries.length - 1) % entries.length;
        else if (event.key === "Home") next = 0;
        else if (event.key === "End") next = entries.length - 1;
        else return;
        event.preventDefault();
        activate(next, true);
      });
    });
    container.dataset.enhanced = "true";
    const initial = entries.findIndex(({ radio }) => radio.checked);
    activate(initial < 0 ? 0 : initial);
  });
})();

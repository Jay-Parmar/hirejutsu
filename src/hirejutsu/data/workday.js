// Reads Workday application pages for hirejutsu, see browser.py. Run as page.evaluate(script, [action, argument]).
// It never changes what a form holds. It only marks elements with data-hirejutsu-* attributes so
// browser.py can click and type into them.
([action, argument]) => {
  const FIELD = '[data-automation-id^="formField-"]';
  const SECTION = '[role="group"][aria-labelledby$="-section"], [data-automation-id$="Section"]';
  const PANEL = '[role="group"][aria-labelledby$="-panel"]';
  // Entries of repeating sections on older pages, like workExperience-2.
  const OLD_PANEL = /^(workExperience|education|websitePanelSet)-\d+$/;
  // The step on older pages without a progress bar.
  const STEP_PAGE = /^(applyFlow\w+Page|contactInformationPage|myExperiencePage|voluntaryDisclosuresPage|selfIdentificationPage)$/;
  const PROMPT = '[data-automation-id="multiSelectContainer"], [data-automation-id="multiselectInputContainer"], [data-automation-id="searchBox"]';
  const DATE_PART = '[data-automation-id^="dateSection"][data-automation-id$="-input"]';
  const OPTIONS = { select: '[role="option"]', prompt: '[data-automation-id="promptOption"]' };

  const shown = (element) => element.getClientRects().length > 0;
  const clean = (text) => (text || '').replace(/\*/g, '').replace(/\s+/g, ' ').trim();
  const automationId = (element) => element.getAttribute('data-automation-id') || '';
  const has = (box, selector) => box.matches(selector) || box.querySelector(selector) !== null;
  const own = (box, selector) => (box.matches(selector) ? box : box.querySelector(selector));
  const unmark = (name) => document.querySelectorAll(`[${name}]`).forEach((element) => element.removeAttribute(name));
  const labelFor = (element) => element.id && document.querySelector(`label[for="${CSS.escape(element.id)}"]`);

  function isPanel(element) {
    return element.matches(PANEL) || OLD_PANEL.test(automationId(element));
  }

  function panelOf(element) {
    for (let node = element.parentElement; node; node = node.parentElement) {
      if (isPanel(node)) return node;
    }
    return null;
  }

  function heading(group) {
    const id = group.getAttribute('aria-labelledby');
    const title = (id && document.getElementById(id)) || group.querySelector('h2, h3, h4');
    return clean(title ? title.textContent : automationId(group));
  }

  function panels(section) {
    return [...section.querySelectorAll('*')].filter((element) => isPanel(element) && shown(element));
  }

  // The label of a field box: its legend or first label, else the label of its control.
  function titleOf(box) {
    const control = own(box, 'input, textarea, button');
    return box.querySelector('legend') || box.querySelector('label') || (control && labelFor(control)) || null;
  }

  function choices(box) {
    return [...box.querySelectorAll('input[type="radio"], input[type="checkbox"]')].map((input) => {
      const label = labelFor(input) || input.closest('label');
      return { input, label, text: clean(label ? label.textContent : input.getAttribute('aria-label') || input.value) };
    });
  }

  function kindOf(box) {
    if (has(box, 'input[type="file"]')) return 'file';
    if (has(box, DATE_PART)) return 'date';
    if (has(box, PROMPT)) return 'prompt';
    if (has(box, 'button[aria-haspopup="listbox"]')) return 'select';
    if (has(box, 'input[type="radio"]')) return 'radio';
    const boxes = choices(box).length;
    if (boxes) return boxes === 1 ? 'checkbox' : 'checkboxes';
    if (has(box, 'textarea')) return 'textarea';
    if (has(box, 'input')) return 'text';
    return 'other';
  }

  function valueOf(box, kind) {
    if (kind === 'text' || kind === 'textarea') return own(box, 'textarea, input:not([type="hidden"])').value.trim();
    if (kind === 'select') {
      const button = own(box, 'button[aria-haspopup="listbox"]');
      const text = clean(button.textContent);
      // Nothing picked shows as Select One, and newer pages give the button an empty value.
      return button.getAttribute('value') === '' || /^select one$/i.test(text) ? '' : text;
    }
    if (kind === 'prompt') {
      const picked = [...box.querySelectorAll('[data-automation-id="selectedItem"]')];
      return picked.map((item) => clean(item.textContent)).join(', ');
    }
    if (kind === 'date') return [...box.querySelectorAll(DATE_PART)].map((input) => input.value).filter(Boolean).join('/');
    if (kind === 'file') {
      const uploaded = box.querySelector('[data-automation-id="file-upload-item"], [data-automation-id="file-upload-successful"]');
      return uploaded || own(box, 'input[type="file"]').files.length ? 'uploaded' : '';
    }
    return choices(box).filter((choice) => choice.input.checked).map((choice) => choice.text).join(', ');
  }

  function step() {
    const active = document.querySelector('[data-automation-id="progressBarActiveStep"]');
    if (active) {
      const labels = [...active.querySelectorAll('label')].map((label) => clean(label.textContent)).filter(Boolean);
      return labels.length ? labels.join(' ') : clean(active.textContent);
    }
    const page = [...document.querySelectorAll('[data-automation-id]')].find((element) => STEP_PAGE.test(automationId(element)));
    return page ? automationId(page) : '';
  }

  function fields() {
    unmark('data-hirejutsu-field');
    const boxes = [...document.querySelectorAll(FIELD)].filter(
      // Workday hides a box called beecatcher that only robots fill in.
      (box) => !box.parentElement.closest(FIELD) && shown(box) && !box.querySelector('[data-automation-id="beecatcher"]'),
    );
    return boxes.map((box, ref) => {
      box.setAttribute('data-hirejutsu-field', ref);
      const kind = kindOf(box);
      const title = titleOf(box);
      const ids = [box, ...box.querySelectorAll('[data-automation-id]')].map((element) => automationId(element).replace(/^formField-/, ''));
      const section = box.closest(SECTION);
      const panel = panelOf(box);
      return {
        ref,
        ids: [...new Set(ids.filter(Boolean))],
        label: clean(title ? title.textContent : ''),
        kind,
        value: valueOf(box, kind),
        required: box.querySelector('[aria-required="true"]') !== null || (title !== null && title.textContent.includes('*')),
        section: section ? heading(section) : '',
        entry: section && panel ? panels(section).indexOf(panel) + 1 : 0,
        options: kind === 'radio' || kind === 'checkboxes' ? choices(box).map((choice) => choice.text) : [],
      };
    });
  }

  // The options of the open dropdown or search list, marked so one can be clicked.
  function options(kind) {
    unmark('data-hirejutsu-option');
    const shownOptions = [...document.querySelectorAll(OPTIONS[kind])].filter(
      (option) => shown(option) && !option.closest('[data-automation-id="selectedItemList"]'),
    );
    return shownOptions.map((option, index) => {
      option.setAttribute('data-hirejutsu-option', index);
      return clean(option.getAttribute('data-automation-label') || option.textContent);
    });
  }

  // The radio buttons or check boxes of a field, marked where a person would click them.
  function choicesOf(ref) {
    unmark('data-hirejutsu-choice');
    const box = document.querySelector(`[data-hirejutsu-field="${ref}"]`);
    return (box ? choices(box) : []).map((choice, index) => {
      (choice.label || choice.input).setAttribute('data-hirejutsu-choice', index);
      return choice.text;
    });
  }

  const actions = { step, fields, options, choices: choicesOf };
  return actions[action](argument);
}

// Stand-ins for the Workday widgets on the test pages. The markup they draw copies what Workday
// pages show; the real widgets are React components.
(() => {
  const closePopups = () => document.querySelectorAll('.popup').forEach((popup) => popup.remove());

  function popup(role) {
    closePopups();
    const list = document.createElement('ul');
    list.className = 'popup';
    list.setAttribute('role', role);
    document.body.appendChild(list);
    return list;
  }

  // A dropdown: a button that opens a list of role=option items.
  function openDropdown(button) {
    const list = popup('listbox');
    for (const text of button.dataset.options.split('|')) {
      const item = document.createElement('li');
      item.setAttribute('role', 'option');
      item.innerHTML = '<div></div>';
      item.firstChild.textContent = text;
      item.addEventListener('click', () => {
        button.textContent = text;
        button.setAttribute('value', text.toLowerCase());
        closePopups();
      });
      list.appendChild(item);
    }
  }

  // A search prompt: Enter lists the matching promptOption items, a click picks one.
  function search(input) {
    const container = input.closest('[data-automation-id="multiSelectContainer"]');
    const typed = input.value.toLowerCase();
    const list = popup('listbox');
    for (const text of container.dataset.options.split('|')) {
      if (!text.toLowerCase().includes(typed)) continue;
      const item = document.createElement('li');
      item.setAttribute('role', 'option');
      item.innerHTML = '<div data-automation-id="promptOption"></div>';
      item.firstChild.textContent = text;
      item.firstChild.setAttribute('data-automation-label', text);
      item.addEventListener('click', () => pick(container, text));
      list.appendChild(item);
    }
  }

  function pick(container, text) {
    const picked = container.querySelector('[data-automation-id="selectedItemList"]');
    if (container.dataset.single) picked.innerHTML = '';
    const item = document.createElement('li');
    item.innerHTML = '<div role="option" data-automation-id="selectedItem"><p data-automation-id="promptOption"></p></div>';
    item.querySelector('p').textContent = text;
    item.querySelector('p').setAttribute('data-automation-label', text);
    picked.appendChild(item);
    container.querySelector('input').value = '';
  }

  // An Add button: a new entry from the section's template, numbered after the ones before it.
  function addEntry(button) {
    const section = button.closest('[role="group"]');
    const number = section.querySelectorAll('[role="group"][aria-labelledby$="-panel"]').length + 1;
    const html = document.getElementById(button.dataset.template).innerHTML.replaceAll('{n}', number);
    button.parentElement.insertAdjacentHTML('beforebegin', html);
    button.textContent = 'Add Another';
  }

  document.addEventListener('click', (event) => {
    const dropdown = event.target.closest('button[aria-haspopup="listbox"]');
    const add = event.target.closest('[data-automation-id="add-button"]');
    if (dropdown) openDropdown(dropdown);
    if (add) addEntry(add);
    if (event.target.closest('[data-automation-id="pageFooterNextButton"]')) document.body.dataset.next = 'clicked';
  });

  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') closePopups();
    if (event.key === 'Enter' && event.target.closest('[data-automation-id="multiSelectContainer"]')) search(event.target);
  });

  document.addEventListener('change', (event) => {
    if (event.target.type !== 'file') return;
    const item = document.createElement('div');
    item.setAttribute('data-automation-id', 'file-upload-item');
    item.textContent = event.target.files[0].name;
    event.target.parentElement.appendChild(item);
  });
})();

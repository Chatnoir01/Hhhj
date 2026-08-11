const button = document.querySelector('#actionButton');
const status = document.querySelector('#status');

button.addEventListener('click', () => {
  status.textContent = '✅ Ça fonctionne : le JavaScript de Moji Tube est actif.';
  button.textContent = 'Application testée !';
});

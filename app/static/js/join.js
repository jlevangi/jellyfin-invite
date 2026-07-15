form.addEventListener('submit', async event => {
  event.preventDefault();
  message.hidden = false;
  message.className = 'msg';
  message.textContent = 'Creating account...';
  try {
    const response = await fetch('/api/activate', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({email: email.value, code: code.value}),
    });
    const json = await response.json();
    if (!response.ok || !json.ok) throw Error(json.message || 'Activation failed.');
    document.getElementById('form').hidden = true;
    message.className = 'msg ok';
    message.textContent = json.message;
    next.hidden = false;
    guideSeparator.hidden = false;
    guide.hidden = false;
  } catch (error) {
    message.className = 'msg err';
    message.textContent = error.message || 'Activation failed. Contact Pierce.';
  }
});

(function () {
  const toggleButton = document.getElementById('jobs-toggle');
  const panel = document.getElementById('jobs-panel');
  const badge = document.getElementById('jobs-badge');
  const list = document.getElementById('jobs-list');

  if (!toggleButton || !panel || !badge || !list) {
    return;
  }

  toggleButton.addEventListener('click', () => {
    panel.classList.toggle('hidden');
  });

  async function refreshActiveDownloads() {
    try {
      const response = await fetch('/active-downloads');
      if (!response.ok) {
        return;
      }

      const data = await response.json();
      badge.textContent = String(data.count || 0);

      if (!data.jobs || data.jobs.length === 0) {
        list.innerHTML = '<li class="jobs-empty">No active downloads</li>';
        return;
      }

      list.innerHTML = data.jobs
        .map(
          (job) => `
          <li class="job-item">
            <div class="job-row">
              <a href="/download/${job.job_id}" class="job-title">${job.book_title}</a>
              <span class="job-meta">${job.current}/${job.total} (${job.percent}%)</span>
            </div>
            <div class="job-progress-wrap">
              <div class="job-progress-bar" style="width:${job.percent}%;"></div>
            </div>
            <p class="job-message">${job.message}</p>
          </li>
        `
        )
        .join('');
    } catch (error) {
      // no-op polling failure
    }
  }

  refreshActiveDownloads();
  setInterval(refreshActiveDownloads, 2000);
})();

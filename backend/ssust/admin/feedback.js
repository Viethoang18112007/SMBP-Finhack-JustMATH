// The team-only feedback page: asks for the admin token, then reads GET /api/admin/feedback with
// "Authorization: Bearer <token>". The token stays in this page's memory (never in the URL or in
// storage). Every value is written with textContent: feedback text is never run as HTML.
(function () {
  "use strict";
  var form = document.getElementById("login");
  var status = document.getElementById("status");
  var table = document.getElementById("list");
  var body = table.querySelector("tbody");
  var summary = document.getElementById("summary");

  function cell(row, text) {
    var td = document.createElement("td");
    td.textContent = text == null ? "" : String(text);
    row.appendChild(td);
  }

  function show(data) {
    body.textContent = "";
    var ratings = [0, 0, 0, 0, 0];
    data.feedback.forEach(function (entry) {
      var row = document.createElement("tr");
      cell(row, entry.createdAt.replace("T", " ").replace("Z", ""));
      cell(row, entry.rating == null ? "" : entry.rating + " / 5");
      cell(row, entry.screen);
      cell(row, entry.contextId);
      cell(row, entry.message);
      cell(row, entry.appVersion);
      cell(row, entry.deviceId ? entry.deviceId.slice(0, 8) : "");
      body.appendChild(row);
      if (entry.rating) ratings[entry.rating - 1] += 1;
    });
    table.hidden = data.count === 0;
    summary.textContent = data.count + " entries. Ratings 1 to 5: " + ratings.join(" / ");
    status.textContent = data.count ? "" : "No feedback yet.";
  }

  form.addEventListener("submit", function (event) {
    event.preventDefault();
    var token = document.getElementById("token").value.trim();
    if (!token) return;
    status.textContent = "Loading…";
    fetch("/api/admin/feedback", { headers: { Authorization: "Bearer " + token }, cache: "no-store" })
      .then(function (res) {
        if (res.status === 401) throw new Error("Wrong token.");
        if (!res.ok) throw new Error("The server refused (" + res.status + ").");
        return res.json();
      })
      .then(show)
      .catch(function (err) {
        table.hidden = true;
        summary.textContent = "";
        status.textContent = err.message;
      });
  });
})();

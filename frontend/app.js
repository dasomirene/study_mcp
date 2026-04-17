    const result = document.getElementById("result");
    const logsSection = document.getElementById("logs");
    const logList = document.getElementById("log-list");
    const chatForm = document.getElementById("chat-form");
    const chatInput = document.getElementById("chat-input");
    const chatMessages = document.getElementById("chat-messages");
    const chatButton = document.getElementById("chat-button");
    const openaiLight = document.getElementById("openai-light");
    const socketLight = document.getElementById("socket-light");
    const weatherapiLight = document.getElementById("weatherapi-light");
    const sessionLabel = document.getElementById("session-label");
    const clearChatButton = document.getElementById("clear-chat-button");
    const moonImageUrl = "https://svs.gsfc.nasa.gov/vis/a000000/a005000/a005001/moon_mosaic_searchweb.png";
    const HOST_ORIGIN = window.location.port === "5500" ? "http://127.0.0.1:8000" : window.location.origin;
    let socket;
    let pendingChatEntry = null;
    let streamingAssistantMessage = null;
    let previousResultState = null;
    let loadingStartedAt = 0;
    const MIN_LOADING_TIME = 650;

    function setResult(html, state = "") {
      if (state !== "loading") {
        previousResultState = null;
      }
      result.className = state ? `result ${state}` : "result";
      result.innerHTML = html;
    }

    function setServiceLight(element, connected, message = "") {
      element.classList.toggle("connected", Boolean(connected));
      element.classList.toggle("error", connected === false);
      element.title = message;
    }

    async function refreshServiceStatus() {
      try {
        const response = await fetch(`${HOST_ORIGIN}/status`, { cache: "no-store" });
        const status = await response.json();
        setServiceLight(
          openaiLight,
          status.openai && status.openai.connected,
          status.openai ? `${status.openai.message || ""} ${status.openai.model || ""}`.trim() : "OpenAI 상태 확인 실패",
        );
        setServiceLight(
          weatherapiLight,
          status.weatherapi && status.weatherapi.connected,
          status.weatherapi ? status.weatherapi.message || "" : "WeatherAPI 상태 확인 실패",
        );
      } catch {
        setServiceLight(openaiLight, false, "상태 API 호출 실패");
        setServiceLight(weatherapiLight, false, "상태 API 호출 실패");
      }
    }

    function setLogs(logs = []) {
      if (!logs.length) {
        logsSection.classList.add("hidden");
        logList.innerHTML = "";
        return;
      }

      logsSection.classList.remove("hidden");
      logList.innerHTML = logs.map((log) => `
        <article class="log-card">
          <div class="log-head">
            <p class="log-name">${escapeHtml(log.title || "-")}</p>
            <div class="log-badges">
              <span class="log-badge ${escapeHtml(log.service || "local")}">${escapeHtml(log.service || "local")}</span>
              <span class="log-badge ${log.status === "error" ? "error" : ""}">${escapeHtml(log.status || "-")}</span>
            </div>
          </div>
          <p class="log-label">Request</p>
          <pre class="log-code">${escapeHtml(JSON.stringify(log.request || {}, null, 2))}</pre>
          <p class="log-label">Response</p>
          <pre class="log-code">${escapeHtml(JSON.stringify(log.response || {}, null, 2))}</pre>
        </article>
      `).join("");
    }

    function resetChatView() {
      chatMessages.innerHTML = `
        <div class="chat-entry assistant">
          <div class="chat-message assistant">대화를 지웠어요. 새로 궁금한 지역과 날짜를 물어보세요.</div>
          <div class="chat-time">지금</div>
        </div>
      `;
      setLogs();
      setResult("질문을 보내면 정리된 날씨와 달 정보가 여기에 표시됩니다.", "empty");
      removePendingMessage();
      previousResultState = null;
    }

    function addChatMessage(role, text) {
      const entry = document.createElement("div");
      entry.className = `chat-entry ${role}`;

      const message = document.createElement("div");
      message.className = `chat-message ${role}`;
      if (role === "assistant") {
        message.innerHTML = renderMarkdown(text);
      } else {
        message.textContent = text;
      }

      const time = document.createElement("div");
      time.className = "chat-time";
      time.textContent = formatChatTime(new Date());

      entry.appendChild(message);
      entry.appendChild(time);
      chatMessages.appendChild(entry);
      chatMessages.scrollTop = chatMessages.scrollHeight;
      return message;
    }

    function startStreamingAssistantMessage() {
      removePendingMessage();
      const entry = document.createElement("div");
      entry.className = "chat-entry assistant";

      const message = document.createElement("div");
      message.className = "chat-message assistant";
      message.dataset.raw = "";

      const time = document.createElement("div");
      time.className = "chat-time";
      time.textContent = formatChatTime(new Date());

      entry.appendChild(message);
      entry.appendChild(time);
      chatMessages.appendChild(entry);
      chatMessages.scrollTop = chatMessages.scrollHeight;
      streamingAssistantMessage = message;
    }

    function appendStreamingAssistantMessage(delta) {
      if (!streamingAssistantMessage) {
        startStreamingAssistantMessage();
      }

      streamingAssistantMessage.dataset.raw = `${streamingAssistantMessage.dataset.raw || ""}${delta}`;
      streamingAssistantMessage.innerHTML = renderMarkdown(streamingAssistantMessage.dataset.raw);
      chatMessages.scrollTop = chatMessages.scrollHeight;
    }

    function finishStreamingAssistantMessage(finalText) {
      if (!streamingAssistantMessage) {
        addChatMessage("assistant", finalText);
        return;
      }

      streamingAssistantMessage.dataset.raw = finalText;
      streamingAssistantMessage.innerHTML = renderMarkdown(finalText);
      streamingAssistantMessage = null;
      chatMessages.scrollTop = chatMessages.scrollHeight;
    }

    function addPendingMessage() {
      removePendingMessage();

      const entry = document.createElement("div");
      entry.className = "chat-entry assistant pending";

      const message = document.createElement("div");
      message.className = "chat-message assistant pending";
      message.innerHTML = `
        <span class="typing-dots" aria-label="답변 작성 중">
          <span></span><span></span><span></span>
        </span>
      `;

      entry.appendChild(message);
      chatMessages.appendChild(entry);
      chatMessages.scrollTop = chatMessages.scrollHeight;
      pendingChatEntry = entry;
    }

    function removePendingMessage() {
      if (!pendingChatEntry) {
        return;
      }

      pendingChatEntry.remove();
      pendingChatEntry = null;
    }

    function formatChatTime(date) {
      return date.toLocaleTimeString("ko-KR", {
        hour: "2-digit",
        minute: "2-digit",
      });
    }

    function getSkeletonMarkup() {
      return `
        <div class="weather-row" aria-hidden="true">
          <div>
            <div class="skeleton-line skeleton-title"></div>
            <div class="skeleton-line skeleton-desc"></div>
          </div>
          <div class="skeleton-summary">
            <div class="skeleton-temp"></div>
            <div class="skeleton-icon"></div>
          </div>
        </div>
        <div class="detail-grid" aria-hidden="true">
          <div class="detail-item">
            <p class="detail-label">체감</p>
            <div class="skeleton-chip"></div>
          </div>
          <div class="detail-item">
            <p class="detail-label">습도</p>
            <div class="skeleton-chip"></div>
          </div>
          <div class="detail-item">
            <p class="detail-label">바람</p>
            <div class="skeleton-chip"></div>
          </div>
          <div class="detail-item">
            <p class="detail-label">위치</p>
            <div class="skeleton-chip"></div>
          </div>
          <div class="detail-item">
            <p class="detail-label">조회 날짜</p>
            <div class="skeleton-chip"></div>
          </div>
          <div class="detail-item">
            <p class="detail-label">검색어</p>
            <div class="skeleton-chip"></div>
          </div>
        </div>
      `;
    }

    function showLoadingResult() {
      removeLoadingOverlay();
      previousResultState = {
        className: result.className,
        html: result.innerHTML,
      };

      result.classList.add("loading");
      const overlay = document.createElement("div");
      overlay.className = "result-loading-overlay";
      overlay.innerHTML = getSkeletonMarkup();
      result.appendChild(overlay);
    }

    function removeLoadingOverlay() {
      const overlay = result.querySelector(".result-loading-overlay");
      if (overlay) {
        overlay.remove();
      }
      result.classList.remove("loading");
    }

    function restorePreviousResult() {
      if (!previousResultState) {
        removeLoadingOverlay();
        return;
      }

      if (result.querySelector(".result-loading-overlay")) {
        result.className = previousResultState.className;
        result.innerHTML = previousResultState.html;
      } else {
        removeLoadingOverlay();
      }
      previousResultState = null;
    }

    function escapeHtml(value) {
      return String(value)
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
    }

    function renderInlineMarkdown(value) {
      return escapeHtml(value)
        .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
        .replace(/`([^`]+)`/g, "<code>$1</code>");
    }

    function isMarkdownTable(lines, index) {
      return (
        index + 1 < lines.length &&
        lines[index].trim().startsWith("|") &&
        lines[index + 1].trim().startsWith("|") &&
        /^\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?$/.test(lines[index + 1].trim())
      );
    }

    function splitTableRow(line) {
      return line
        .trim()
        .replace(/^\|/, "")
        .replace(/\|$/, "")
        .split("|")
        .map((cell) => cell.trim());
    }

    function renderMarkdownTable(lines, startIndex) {
      const header = splitTableRow(lines[startIndex]);
      let index = startIndex + 2;
      const rows = [];

      while (index < lines.length && lines[index].trim().startsWith("|")) {
        rows.push(splitTableRow(lines[index]));
        index += 1;
      }

      const headHtml = header.map((cell) => `<th>${renderInlineMarkdown(cell)}</th>`).join("");
      const bodyHtml = rows.map((row) => `
        <tr>${row.map((cell) => `<td>${renderInlineMarkdown(cell)}</td>`).join("")}</tr>
      `).join("");

      return {
        html: `<table><thead><tr>${headHtml}</tr></thead><tbody>${bodyHtml}</tbody></table>`,
        nextIndex: index,
      };
    }

    function getHeading(line) {
      const match = line.match(/^\s{0,3}(#{1,3})\s+(.+)$/);
      if (!match) {
        return null;
      }

      return {
        level: match[1].length,
        text: match[2].trim(),
      };
    }

    function getUnorderedListItem(line) {
      const match = line.match(/^\s*[-*+]\s+(.+)$/);
      return match ? match[1].trim() : null;
    }

    function getOrderedListItem(line) {
      const match = line.match(/^\s*\d+[.)]\s+(.+)$/);
      return match ? match[1].trim() : null;
    }

    function splitLabelValueItem(item) {
      const cleaned = item.trim();
      const match = cleaned.match(/^(.{1,32}?)(?:\s*[:：]\s+|\s+-\s+)(.+)$/);
      if (!match) {
        return null;
      }

      const label = match[1].trim().replace(/^\*\*(.+)\*\*$/, "$1");
      const value = match[2].trim();
      if (!label || !value) {
        return null;
      }

      return { label, value };
    }

    function renderKeyValueTable(items) {
      const rows = items
        .map(splitLabelValueItem)
        .filter(Boolean);

      if (rows.length < 2 || rows.length !== items.length) {
        return null;
      }

      const bodyHtml = rows.map((row) => `
        <tr>
          <th>${renderInlineMarkdown(row.label)}</th>
          <td>${renderInlineMarkdown(row.value)}</td>
        </tr>
      `).join("");

      return `<table class="key-value-table"><tbody>${bodyHtml}</tbody></table>`;
    }

    function renderMarkdownList(lines, startIndex, ordered) {
      let index = startIndex;
      const items = [];

      while (index < lines.length) {
        const item = ordered ? getOrderedListItem(lines[index]) : getUnorderedListItem(lines[index]);
        if (item === null) {
          break;
        }

        items.push(item);
        index += 1;
      }

      const tag = ordered ? "ol" : "ul";
      const tableHtml = renderKeyValueTable(items);
      if (tableHtml) {
        return {
          html: tableHtml,
          nextIndex: index,
        };
      }

      const itemHtml = items.map((item) => `<li>${renderInlineMarkdown(item)}</li>`).join("");

      return {
        html: `<${tag}>${itemHtml}</${tag}>`,
        nextIndex: index,
      };
    }

    function renderMarkdown(text) {
      const lines = String(text || "").split("\n");
      const blocks = [];
      let paragraph = [];

      function flushParagraph() {
        if (!paragraph.length) {
          return;
        }
        blocks.push(`<p>${paragraph.map((line) => renderInlineMarkdown(line)).join("<br>")}</p>`);
        paragraph = [];
      }

      for (let index = 0; index < lines.length;) {
        const line = lines[index];
        if (isMarkdownTable(lines, index)) {
          flushParagraph();
          const table = renderMarkdownTable(lines, index);
          blocks.push(table.html);
          index = table.nextIndex;
          continue;
        }

        const heading = getHeading(line);
        if (heading) {
          flushParagraph();
          blocks.push(`<h${heading.level}>${renderInlineMarkdown(heading.text)}</h${heading.level}>`);
          index += 1;
          continue;
        }

        if (getUnorderedListItem(line) !== null) {
          flushParagraph();
          const list = renderMarkdownList(lines, index, false);
          blocks.push(list.html);
          index = list.nextIndex;
          continue;
        }

        if (getOrderedListItem(line) !== null) {
          flushParagraph();
          const list = renderMarkdownList(lines, index, true);
          blocks.push(list.html);
          index = list.nextIndex;
          continue;
        }

        if (!line.trim()) {
          flushParagraph();
          index += 1;
          continue;
        }

        paragraph.push(line.trim());
        index += 1;
      }

      flushParagraph();
      return blocks.join("");
    }

    function formatNumber(value, suffix = "") {
      if (value === null || value === undefined || Number.isNaN(Number(value))) {
        return "-";
      }

      return `${Math.round(Number(value))}${suffix}`;
    }

    function normalizeMoonPhase(phase) {
      return String(phase || "")
        .trim()
        .toLowerCase()
        .replaceAll("_", " ")
        .replaceAll("-", " ")
        .replace(/\s+/g, " ");
    }

    function getMoonClass(phase) {
      const normalizedPhase = normalizeMoonPhase(phase);
      const classes = {
        "new moon": "new-moon",
        "waxing crescent": "waxing-crescent",
        "first quarter": "first-quarter",
        "waxing gibbous": "waxing-gibbous",
        "full moon": "full-moon",
        "waning gibbous": "waning-gibbous",
        "last quarter": "last-quarter",
        "waning crescent": "waning-crescent",
      };

      return classes[normalizedPhase] || "new-moon";
    }

    function getMoonPhaseKo(phase) {
      const normalizedPhase = normalizeMoonPhase(phase);
      const labels = {
        "new moon": "삭",
        "waxing crescent": "초승달",
        "first quarter": "상현달",
        "waxing gibbous": "차가는 볼록달",
        "full moon": "보름달",
        "waning gibbous": "기우는 볼록달",
        "last quarter": "하현달",
        "waning crescent": "그믐달",
      };

      return labels[normalizedPhase] || phase || "알 수 없음";
    }

    function renderWeather(data) {
      setResult(`
        <div class="weather-row">
          <div>
            <p class="weather-place">${escapeHtml(data.location)}${data.country ? `, ${escapeHtml(data.country)}` : ""}</p>
            <p class="weather-desc">${escapeHtml(data.weather)}</p>
          </div>
          <div class="weather-summary">
            <div class="temperature">${escapeHtml(formatNumber(data.temp, "°C"))}</div>
            ${data.icon ? `<img class="weather-icon" src="${escapeHtml(data.icon)}" alt="">` : ""}
          </div>
        </div>
        <div class="detail-grid">
          <div class="detail-item">
            <p class="detail-label">체감</p>
            <p class="detail-value">${escapeHtml(formatNumber(data.feelslike, "°C"))}</p>
          </div>
          <div class="detail-item">
            <p class="detail-label">습도</p>
            <p class="detail-value">${escapeHtml(formatNumber(data.humidity, "%"))}</p>
          </div>
          <div class="detail-item">
            <p class="detail-label">바람</p>
            <p class="detail-value">${escapeHtml(formatNumber(data.wind, " km/h"))}</p>
          </div>
          <div class="detail-item">
            <p class="detail-label">위치</p>
            <p class="detail-value">${escapeHtml(data.country || "-")}</p>
          </div>
          <div class="detail-item">
            <p class="detail-label">조회 날짜</p>
            <p class="detail-value">${escapeHtml(data.date || data.localtime || "-")}</p>
          </div>
          <div class="detail-item">
            <p class="detail-label">검색어</p>
            <p class="detail-value">${escapeHtml(data.query || "-")}</p>
          </div>
        </div>
      `);
    }

    function renderAstronomy(data) {
      const moonLabel = data.moon_phase_ko || getMoonPhaseKo(data.moon_phase);
      const moonClass = getMoonClass(data.moon_phase);
      const astronomyDateLabel = data.date ? `${data.date} 달과 해 흐름` : "달과 해 흐름";

      setResult(`
        <div class="astronomy-layout">
          <div class="moon-stage">
            <div class="moon ${escapeHtml(moonClass)}" aria-label="${escapeHtml(moonLabel)}">
              <img class="moon-image" src="${moonImageUrl}" alt="">
            </div>
            <div>
              <p class="moon-label">${escapeHtml(moonLabel)}</p>
              <p class="moon-illumination">${escapeHtml(data.moon_phase)}</p>
            </div>
          </div>
          <div>
            <p class="weather-place">${escapeHtml(data.location)}${data.country ? `, ${escapeHtml(data.country)}` : ""}</p>
            <p class="weather-desc">${escapeHtml(astronomyDateLabel)}</p>
          </div>
        </div>
        <div class="detail-grid">
          <div class="detail-item">
            <p class="detail-label">월출</p>
            <p class="detail-value">${escapeHtml(data.moonrise)}</p>
          </div>
          <div class="detail-item">
            <p class="detail-label">월몰</p>
            <p class="detail-value">${escapeHtml(data.moonset)}</p>
          </div>
          <div class="detail-item">
            <p class="detail-label">달 모양</p>
            <p class="detail-value">${escapeHtml(data.moon_shape_description || "-")}</p>
          </div>
          <div class="detail-item">
            <p class="detail-label">일출</p>
            <p class="detail-value">${escapeHtml(data.sunrise)}</p>
          </div>
          <div class="detail-item">
            <p class="detail-label">일몰</p>
            <p class="detail-value">${escapeHtml(data.sunset)}</p>
          </div>
          <div class="detail-item">
            <p class="detail-label">달 위상</p>
            <p class="detail-value">${escapeHtml(moonLabel)}</p>
          </div>
        </div>
      `);
    }

    function handleSocketData(data) {
      removePendingMessage();
      if (data.type === "session") {
        sessionLabel.textContent = `Session ${String(data.session_id || "").slice(0, 8)}`;
        return;
      }

      if (data.type === "clear_history") {
        return;
      }

      if (data.type === "chat_start") {
        setLogs(data.logs || []);
        startStreamingAssistantMessage();
        if (data.result && !data.result.error) {
          if (data.intent && data.intent.type === "astronomy") {
            renderAstronomy(data.result);
          } else {
            renderWeather(data.result);
          }
        } else {
          restorePreviousResult();
        }
        return;
      }

      if (data.type === "chat_delta") {
        appendStreamingAssistantMessage(data.delta || "");
        return;
      }

      if (data.type === "chat_done") {
        finishStreamingAssistantMessage(data.answer || "답변을 만들지 못했습니다.");
        setLogs(data.logs || []);
        chatButton.disabled = false;
        chatButton.textContent = "전송";
        return;
      }

      setLogs(data.logs || []);

      if (data.type === "chat") {
        addChatMessage("assistant", data.answer || data.error || "답변을 만들지 못했습니다.");
        if (data.result && !data.result.error) {
          if (data.intent && data.intent.type === "astronomy") {
            renderAstronomy(data.result);
          } else {
            renderWeather(data.result);
          }
        } else {
          restorePreviousResult();
        }
        chatButton.disabled = false;
        chatButton.textContent = "전송";
        return;
      }

      if (data.error) {
        setResult(`
          <div class="error">
            <strong>조회에 실패했습니다.</strong>
            ${escapeHtml(data.error)}
          </div>
        `);
      } else if (data.type === "astronomy") {
        renderAstronomy(data);
      } else {
        renderWeather(data);
      }

      chatButton.disabled = false;
      chatButton.textContent = "전송";
    }

    function connectSocket() {
      const hostUrl = new URL(HOST_ORIGIN);
      const protocol = hostUrl.protocol === "https:" ? "wss:" : "ws:";
      socket = new WebSocket(`${protocol}//${hostUrl.host}/ws`);

      socket.onopen = () => {
        setServiceLight(socketLight, true, "WebSocket 연결됨");
      };

      socket.onmessage = (event) => {
        const data = JSON.parse(event.data);
        const elapsed = Date.now() - loadingStartedAt;
        const remaining = Math.max(0, MIN_LOADING_TIME - elapsed);

        if (remaining > 0) {
          setTimeout(() => handleSocketData(data), remaining);
          return;
        }

        handleSocketData(data);
      };

      socket.onclose = () => {
        setServiceLight(socketLight, false, "WebSocket 연결 끊김");
        setTimeout(connectSocket, 900);
      };
    }

    refreshServiceStatus();
    setInterval(refreshServiceStatus, 60000);
    connectSocket();

    function sendChatMessage(message) {
      const trimmedMessage = message.trim();
      if (!trimmedMessage) {
        chatInput.focus();
        return;
      }

      addChatMessage("user", trimmedMessage);
      addPendingMessage();
      chatInput.value = "";
      chatButton.disabled = true;
      chatButton.textContent = "전송 중";
      setLogs();
      loadingStartedAt = Date.now();
      showLoadingResult();

      const payload = {
        type: "chat",
        message: trimmedMessage,
      };

      if (socket && socket.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify(payload));
        return;
      }

      connectSocket();
      setTimeout(() => {
        if (socket && socket.readyState === WebSocket.OPEN) {
          socket.send(JSON.stringify(payload));
          return;
        }

        addChatMessage("assistant", "WebSocket 연결을 준비하지 못했습니다. 잠시 후 다시 시도해주세요.");
        removePendingMessage();
        restorePreviousResult();
        chatButton.disabled = false;
        chatButton.textContent = "전송";
      }, 600);
    }

    chatForm.addEventListener("submit", (event) => {
      event.preventDefault();
      sendChatMessage(chatInput.value);
    });

    clearChatButton.addEventListener("click", () => {
      resetChatView();
      if (socket && socket.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify({ type: "clear_history" }));
      }
      chatInput.focus();
    });

const tg = window.Telegram ? window.Telegram.WebApp : null;
if (tg) {
  tg.ready();
  tg.expand();
}

const params = new URLSearchParams(window.location.search);
const defaultChatId = window.WEBAPP_DEFAULT_CHAT_ID ?? null;
const defaultThreadId = window.WEBAPP_DEFAULT_THREAD_ID ?? null;
const chatId = params.get("chat_id") || defaultChatId;
const threadId = params.get("thread_id") || defaultThreadId;
const statePayload = {
  init_data: tg ? tg.initData : "",
  chat_id: chatId ? Number(chatId) : null,
  thread_id: threadId ? Number(threadId) : null,
  login_data: null,
};

const userLine = document.getElementById("userLine");
const loginCard = document.getElementById("loginCard");
const loginStatus = document.getElementById("loginStatus");
const loginForm = document.getElementById("loginForm");
const loginEmail = document.getElementById("loginEmail");
const loginPassword = document.getElementById("loginPassword");
const loginBtn = document.getElementById("loginBtn");
const logoutBtn = document.getElementById("logoutBtn");
const tgLoginWrap = document.getElementById("tgLoginWrap");
const registerForm = document.getElementById("registerForm");
const registerEmail = document.getElementById("registerEmail");
const registerNickname = document.getElementById("registerNickname");
const registerPassword = document.getElementById("registerPassword");
const statsBlock = document.getElementById("statsBlock");
const storageMeta = document.getElementById("storageMeta");
const storageList = document.getElementById("storageList");
const storagePage = document.getElementById("storagePage");
const storagePrev = document.getElementById("storagePrev");
const storageNext = document.getElementById("storageNext");
const storageUpgrade = document.getElementById("storageUpgrade");
const storageNotice = document.getElementById("storageNotice");
const storageSearch = document.getElementById("storageSearch");
const sessionBlock = document.getElementById("sessionBlock");
const eventBlock = document.getElementById("eventBlock");
const actionsBlock = document.getElementById("actionsBlock");
const logBlock = document.getElementById("logBlock");
const sellMeta = document.getElementById("sellMeta");
const sellList = document.getElementById("sellList");
const sellPage = document.getElementById("sellPage");
const sellPrev = document.getElementById("sellPrev");
const sellNext = document.getElementById("sellNext");
const sellSelected = document.getElementById("sellSelected");
const sellNotice = document.getElementById("sellNotice");
const shopMeta = document.getElementById("shopMeta");
const shopStatic = document.getElementById("shopStatic");
const shopOffers = document.getElementById("shopOffers");
const shopRecipe = document.getElementById("shopRecipe");
const shopUpgrade = document.getElementById("shopUpgrade");
const shopNotice = document.getElementById("shopNotice");
const craftList = document.getElementById("craftList");
const craftNotice = document.getElementById("craftNotice");
const blueprintList = document.getElementById("blueprintList");
const blueprintPage = document.getElementById("blueprintPage");
const blueprintPrev = document.getElementById("blueprintPrev");
const blueprintNext = document.getElementById("blueprintNext");
const blueprintNotice = document.getElementById("blueprintNotice");
const loadoutCurrent = document.getElementById("loadoutCurrent");
const loadoutOptions = document.getElementById("loadoutOptions");
const loadoutPage = document.getElementById("loadoutPage");
const loadoutPrev = document.getElementById("loadoutPrev");
const loadoutNext = document.getElementById("loadoutNext");
const loadoutNotice = document.getElementById("loadoutNotice");
const warehouseMeta = document.getElementById("warehouseMeta");
const warehouseOrder = document.getElementById("warehouseOrder");
const warehouseTop = document.getElementById("warehouseTop");
const ratingList = document.getElementById("ratingList");
const caseMeta = document.getElementById("caseMeta");
const caseList = document.getElementById("caseList");
const caseNotice = document.getElementById("caseNotice");
const caseOpen = document.getElementById("caseOpen");
const dailyQuestList = document.getElementById("dailyQuestList");
const weeklyQuestList = document.getElementById("weeklyQuestList");
const questNotice = document.getElementById("questNotice");
const marketMeta = document.getElementById("marketMeta");
const marketItems = document.getElementById("marketItems");
const marketItemsPage = document.getElementById("marketItemsPage");
const marketItemsPrev = document.getElementById("marketItemsPrev");
const marketItemsNext = document.getElementById("marketItemsNext");
const marketSelected = document.getElementById("marketSelected");
const marketPrice = document.getElementById("marketPrice");
const marketNotice = document.getElementById("marketNotice");
const marketListings = document.getElementById("marketListings");
const marketPrev = document.getElementById("marketPrev");
const marketNext = document.getElementById("marketNext");
const marketPage = document.getElementById("marketPage");
const seasonMeta = document.getElementById("seasonMeta");
const seasonList = document.getElementById("seasonList");
const adminForm = document.getElementById("adminForm");
const adminEventBase = document.getElementById("adminEventBase");
const adminGreedMult = document.getElementById("adminGreedMult");
const adminEvacBase = document.getElementById("adminEvacBase");
const adminEvacPenalty = document.getElementById("adminEvacPenalty");
const adminWarehouseGoal = document.getElementById("adminWarehouseGoal");
const adminEventGoal = document.getElementById("adminEventGoal");
const adminSellCap = document.getElementById("adminSellCap");
const adminSellCountCap = document.getElementById("adminSellCountCap");
const adminMarketCap = document.getElementById("adminMarketCap");
const adminSeason1 = document.getElementById("adminSeason1");
const adminSeason2 = document.getElementById("adminSeason2");
const adminSeason3 = document.getElementById("adminSeason3");
const adminSave = document.getElementById("adminSave");
const adminNotice = document.getElementById("adminNotice");
const onboardingModal = document.getElementById("onboardingModal");
const onboardingSteps = document.getElementById("onboardingSteps");
const onboardingDone = document.getElementById("onboardingDone");

const storageState = { page: 1, sort: "rarity" };
const sellState = { page: 1, sort: "rarity", selected: null };
const blueprintState = { page: 1 };
const loadoutState = { page: 1, equipType: null };
const marketState = { itemsPage: 1, page: 1, sort: "rarity", selected: null };
let currentState = null;
let activeTab = "raid";
let authToken = null;
let tgAuthTimer = null;
let tgInitAttempted = false;
function hasAuth() {
  return !!authToken;
}

function toggleAppButtons(disabled) {
  document
    .querySelectorAll("button:not(.tab):not(.auth-btn)")
    .forEach((btn) => {
      btn.disabled = disabled;
    });
}

function toggleAuthButtons(isAuthed) {
  if (loginBtn) loginBtn.classList.toggle("hidden", !!isAuthed);
  if (logoutBtn) logoutBtn.classList.toggle("hidden", !isAuthed);
}

function loadAuthToken() {
  try {
    authToken = localStorage.getItem("raid_auth_token");
    if (authToken) {
      statePayload.auth_token = authToken;
    }
  } catch (e) {
    authToken = null;
  }
}

function setAuthToken(token, user) {
  authToken = token;
  statePayload.auth_token = token;
  try {
    localStorage.setItem("raid_auth_token", token);
  } catch (e) {
    // ignore
  }
  if (loginStatus) {
    const name = user?.nickname || user?.email || "Пользователь";
    loginStatus.textContent = `Авторизован: ${name}`;
  }
  if (loginCard) {
    loginCard.classList.add("hidden");
  }
  toggleAppButtons(false);
  toggleAuthButtons(true);
}

function clearAuthToken(message) {
  authToken = null;
  statePayload.auth_token = null;
  statePayload.init_data = "";
  try {
    localStorage.removeItem("raid_auth_token");
  } catch (e) {
    // ignore
  }
  if (loginStatus) {
    loginStatus.textContent = message || "Авторизация не выполнена.";
  }
  if (loginCard) {
    loginCard.classList.remove("hidden");
  }
  toggleAppButtons(true);
  toggleAuthButtons(false);
  if (userLine) {
    userLine.textContent = "Пилот: —";
  }
}

loadAuthToken();
if (authToken) {
  setAuthToken(authToken);
} else {
  toggleAuthButtons(false);
}
if (!authToken) {
  tryTelegramInitAuth();
}

async function tryTelegramInitAuth() {
  if (tgInitAttempted || authToken) return;
  tgInitAttempted = true;
  if (!tg || !tg.initData) return;
  if (tgLoginWrap) tgLoginWrap.classList.add("hidden");
  if (loginStatus) loginStatus.textContent = "Вход через Telegram...";
  try {
    const res = await apiPostRaw("/api/auth/telegram/init", {
      init_data: tg.initData,
    });
    if (res.ok && res.data && res.data.ok && res.data.token) {
      setAuthToken(res.data.token, res.data.user);
      await refreshCore();
    } else if (loginStatus) {
      const msg =
        (res.data && res.data.message) ||
        `Ошибка авторизации через Telegram. (${res.status})`;
      loginStatus.textContent = msg;
    }
  } catch (err) {
    if (loginStatus) {
      loginStatus.textContent = `Ошибка авторизации через Telegram: ${
        err?.message || "неизвестная ошибка"
      }`;
    }
  }
}

function renderStats(rating) {
  if (!rating) return "—";
  return `
    <div>Очки <span>${rating.points}</span></div>
    <div>Рейды <span>${rating.raids}</span></div>
    <div>Эвак <span>${rating.extracts}</span></div>
    <div>Смерти <span>${rating.deaths}</span></div>
    <div>Убийства <span>${rating.kills}</span></div>
    <div>RC <span>${rating.raidcoins}</span></div>
  `;
}

function renderStorage(storage) {
  if (!storage) return;
  storageMeta.textContent = `Слоты: ${storage.used}/${storage.limit} • Ценность: ${storage.total_value} • Сорт: ${storage.sort_label}`;
  storagePage.textContent = `${storage.page}/${storage.total_pages}`;
  const query = (storageSearch?.value || "").trim().toLowerCase();
  const items = query
    ? storage.items.filter((item) => item.name.toLowerCase().includes(query))
    : storage.items;
  if (!items || items.length === 0) {
    storageList.innerHTML = "<div class='muted'>Пусто.</div>";
  } else {
    storageList.innerHTML = items
      .map(
        (item) => `
        <div class="list-item">
          <div class="item-main">
            <div>${item.emoji} ${item.name} x${item.qty}</div>
            <div class="muted">ценн. ${item.value}</div>
          </div>
        </div>
      `
      )
      .join("");
  }
  const canUpgrade = storage.can_upgrade;
  const upgradeCost = storage.upgrade_cost;
  storageUpgrade.disabled = !canUpgrade || storage.points < upgradeCost;
  storageUpgrade.textContent = canUpgrade
    ? `Улучшить склад (${upgradeCost} очк.)`
    : "Лимит склада максимум";
  document.querySelectorAll(".chip").forEach((chip) => {
    chip.classList.toggle("active", chip.dataset.sort === storage.sort);
  });
}

function renderSell(sell) {
  if (!sell) return;
  sellMeta.textContent = `RC: ${sell.raidcoins} • Сорт: ${sell.sort_label}`;
  sellPage.textContent = `${sell.page}/${sell.total_pages}`;
  if (!sell.items || sell.items.length === 0) {
    sellList.innerHTML = "<div class='muted'>Нечего продавать.</div>";
    sellSelected.textContent = "Выберите предмет для продажи.";
    sellState.selected = null;
    return;
  }
  sellList.innerHTML = sell.items
    .map(
      (item) => `
      <div class="list-item" data-sell-id="${item.id}">
        <div class="item-main">
          <div>${item.emoji} ${item.name} x${item.qty}</div>
          <div class="muted">цена: ${item.unit_price} RC за 1</div>
        </div>
      </div>
    `
    )
    .join("");
  sell.items.forEach((item) => {
    const row = sellList.querySelector(`[data-sell-id="${item.id}"]`);
    if (!row) return;
    row.onclick = () => {
      sellState.selected = item;
      sellSelected.textContent = `Выбрано: ${item.emoji} ${item.name} x${item.qty} (цена за 1: ${item.unit_price} RC)`;
    };
  });
}

function renderSession(session) {
  if (!session) {
    sessionBlock.innerHTML = "<div class='muted'>Нет активного рейда.</div>";
    return;
  }
  const raidItems = session.inventory
    ? Object.values(session.inventory).reduce((a, b) => a + b, 0)
    : 0;
  const statusLabel = session.status === "combat" ? "Бой" : "В рейде";
  const enemyLine =
    session.status === "combat" && session.enemy
      ? `<div>Враг <span>${session.enemy.name} (${session.enemy.hp_current}/${session.enemy.hp})</span></div>`
      : "";
  sessionBlock.innerHTML = `
    <div class="stats">
      <div>Статус <span>${statusLabel}</span></div>
      <div>HP <span>${session.hp}/${session.max_hp}</span></div>
      <div>Алчность <span>${session.greed}</span></div>
      <div>Лут <span>${session.loot_value}</span></div>
      <div>Киллы <span>${session.kills}</span></div>
      <div>Слоты рейда <span>${raidItems}/20</span></div>
      ${enemyLine}
    </div>
  `;
}

function renderEvent(event) {
  if (!event) {
    eventBlock.innerHTML = "<div class='muted'>Событие не активно.</div>";
    return;
  }
  const progress = event.goal
    ? Math.round((event.value_total / event.goal) * 100)
    : 0;
  eventBlock.innerHTML = `
    <div class="stats">
      <div>Период <span>${event.start || "—"} → ${event.end || "—"}</span></div>
      <div>Прогресс <span>${event.value_total}/${event.goal} (${progress}%)</span></div>
      <div>Предметов <span>${event.items_total}</span></div>
    </div>
  `;
}


function renderQuests(quests) {
  if (!quests) return;
  function buildList(list, kind, target) {
    if (!target) return;
    if (!list || list.length === 0) {
      target.innerHTML = "<div class='muted'>Пока нет контрактов.</div>";
      return;
    }
    target.innerHTML = list
      .map((quest) => {
        const progress = quest.target
          ? Math.min(100, Math.round((quest.progress / quest.target) * 100))
          : 0;
        const reward = [];
        if (quest.reward_points) reward.push(`+${quest.reward_points} очк.`);
        if (quest.reward_raidcoins)
          reward.push(`+${quest.reward_raidcoins} RC`);
        const rewardLine = reward.length ? reward.join(" ") : "—";
        const status = quest.claimed
          ? "Получено"
          : quest.completed
          ? "Готово"
          : "В процессе";
        const disabled = !quest.completed || quest.claimed;
        return `
        <div class="list-item">
          <div class="item-main">
            <div>${quest.title}</div>
            <div class="quest-meta">
              <span>${quest.progress}/${quest.target}</span>
              <span>${rewardLine}</span>
              <span>${status}</span>
            </div>
            <div class="progress"><span style="width:${progress}%"></span></div>
          </div>
          <div class="item-actions">
            <button class="btn quest-claim" data-kind="${kind}" data-id="${quest.quest_id}" ${
              disabled ? "disabled" : ""
            }>Забрать</button>
          </div>
        </div>
      `;
      })
      .join("");
    target.querySelectorAll(".quest-claim").forEach((btn) => {
      btn.onclick = async () => {
        const kind = btn.dataset.kind;
        const id = btn.dataset.id;
        const res = await apiPost("/api/quest/claim", {
          ...statePayload,
          kind,
          quest_id: id,
        });
        questNotice.textContent = res.message || "";
        if (res.quests) {
          renderQuests(res.quests);
          await refreshCore();
        }
      };
    });
  }
  buildList(quests.daily || [], "daily", dailyQuestList);
  buildList(quests.weekly || [], "weekly", weeklyQuestList);
}

function renderSeason(season) {
  if (!season) return;
  if (season.season) {
    seasonMeta.textContent = `Сезон ${season.season.id}: ${season.season.start} → ${season.season.end}`;
  }
  if (!season.top || season.top.length === 0) {
    seasonList.innerHTML = "<div class='muted'>Нет данных.</div>";
    return;
  }
  seasonList.innerHTML = season.top
    .map(
      (row, idx) => `
      <div class="list-item">
        <div class="item-main">
          <div>#${idx + 1} ${row.name}</div>
          <div class="muted">Очки ${row.points} • Рейды ${row.raids} • Эвак ${row.extracts}</div>
        </div>
      </div>
    `
    )
    .join("");
}

function renderOnboarding(data) {
  if (!onboardingModal || !onboardingSteps || !onboardingDone) return;
  if (!data.onboarding_required) {
    onboardingModal.classList.add("hidden");
    return;
  }
  onboardingSteps.innerHTML = (data.onboarding_steps || [])
    .map((step) => `<div class="list-item"><div class="item-main">${step}</div></div>`)
    .join("");
  onboardingModal.classList.remove("hidden");
}

function renderAdminFlag(data) {
  const adminTabs = document.querySelectorAll(".admin-tab");
  const adminViews = document.querySelectorAll(".admin-view");
  const show = !!data.is_admin;
  adminTabs.forEach((tab) => tab.classList.toggle("hidden", !show));
  adminViews.forEach((view) => view.classList.toggle("hidden", !show));
}

function renderMarket(market) {
  if (!market) return;
  marketMeta.textContent = `RC: ${market.raidcoins} • лимит лотов: ${market.listing_cap}`;
  marketItemsPage.textContent = `${market.items_page}/${market.items_total_pages}`;
  if (!market.items || market.items.length === 0) {
    marketItems.innerHTML = "<div class='muted'>Нет предметов.</div>";
  } else {
    marketItems.innerHTML = market.items
      .map(
        (item) => `
      <div class="list-item" data-market-id="${item.id}">
        <div class="item-main">
          <div>${item.emoji} ${item.name} x${item.qty}</div>
          <div class="muted">база: ${item.unit_price} RC</div>
        </div>
      </div>
    `
      )
      .join("");
  }
  const selectedId = marketState.selected ? marketState.selected.id : null;
  if (selectedId && !(market.items || []).some((i) => i.id === selectedId)) {
    marketState.selected = null;
    if (marketSelected) marketSelected.textContent = "Выберите предмет для лота.";
  }
  market.items?.forEach((item) => {
    const row = marketItems.querySelector(`[data-market-id="${item.id}"]`);
    if (!row) return;
    row.onclick = () => {
      marketState.selected = item;
      marketSelected.textContent = `Выбрано: ${item.emoji} ${item.name} x${item.qty}`;
    };
  });

  marketPage.textContent = `${market.page}/${market.total_pages}`;
  const myIds = new Set((market.my_listings || []).map((l) => l.id));
  if (!market.listings || market.listings.length === 0) {
    marketListings.innerHTML = "<div class='muted'>Лоты пусты.</div>";
  } else {
    marketListings.innerHTML = market.listings
      .map((lot) => {
        const isMine = myIds.has(lot.id);
        return `
        <div class="list-item">
          <div class="item-main">
            <div>${lot.emoji} ${lot.name} x${lot.qty}</div>
            <div class="muted">${lot.price} RC • продавец: ${lot.seller_name}</div>
          </div>
          <div class="item-actions">
            <button class="btn ${isMine ? "lot-cancel" : "lot-buy"}" data-id="${lot.id}">${
              isMine ? "Снять" : "Купить"
            }</button>
          </div>
        </div>
      `;
      })
      .join("");
  }
  marketListings.querySelectorAll(".lot-buy").forEach((btn) => {
    btn.onclick = async () => {
      const id = btn.dataset.id;
      const res = await apiPost("/api/market/buy", {
        ...statePayload,
        listing_id: Number(id),
      });
      marketNotice.textContent = res.message || "";
      if (res.market) renderMarket(res.market);
      await refreshCore();
    };
  });
  marketListings.querySelectorAll(".lot-cancel").forEach((btn) => {
    btn.onclick = async () => {
      const id = btn.dataset.id;
      const res = await apiPost("/api/market/cancel", {
        ...statePayload,
        listing_id: Number(id),
      });
      marketNotice.textContent = res.message || "";
      if (res.market) renderMarket(res.market);
      await refreshCore();
    };
  });
}

function renderActions(state) {
  actionsBlock.innerHTML = "";
  if (!state) {
    actionsBlock.textContent = "—";
    return;
  }
  const session = state.session;
  const cooldowns = state.cooldowns || {};
  const pendingItem = state.pending_item;

  function addButton(label, action, disabled) {
    const btn = document.createElement("button");
    btn.className = "btn";
    btn.textContent = label;
    btn.disabled = !!disabled;
    btn.onclick = () => handleAction(action);
    actionsBlock.appendChild(btn);
  }

  if (!session) {
    addButton("Войти в рейд", "enter", false);
    return;
  }

  if (session.pending_choice) {
    const pending = session.pending_choice;
    const choices = pending.choices || [];
    if (pending.text) {
      logBlock.textContent = pending.text;
    }
    if (choices.length) {
      choices.forEach((choice) => {
        addButton(choice.label || "Выбрать", `choice:${choice.id}`, false);
      });
      return;
    }
  }

  if (pendingItem) {
    const label = `${pendingItem.emoji ? pendingItem.emoji + " " : ""}${
      pendingItem.name
    }`;
    logBlock.textContent = `Найден предмет: ${label}`;
    addButton("Взять", "take", false);
    addButton("Не брать", "skip", false);
    return;
  }

  if (session.status === "combat") {
    const fightCd = cooldowns.fight || 0;
    addButton(
      fightCd > 0 ? `Сражаться (${fightCd}с)` : "Сражаться",
      "fight",
      fightCd > 0
    );
    if (state.can_medkit) {
      const medCd = cooldowns.medkit || 0;
      addButton(
        medCd > 0 ? `Расходник (${medCd}с)` : "Расходник",
        "medkit",
        medCd > 0
      );
    }
    return;
  }

  const lootCd = cooldowns.loot || 0;
  const moveCd = cooldowns.move || 0;
  const evacCd = cooldowns.evac || 0;
  addButton(lootCd > 0 ? `Лутать (${lootCd}с)` : "Лутать", "loot", lootCd > 0);
  addButton(
    moveCd > 0 ? `Идти дальше (${moveCd}с)` : "Идти дальше",
    "move",
    moveCd > 0
  );
  addButton(
    evacCd > 0 ? `Эвакуация (${evacCd}с)` : "Эвакуация",
    "evac",
    evacCd > 0
  );
  if (state.can_medkit) {
    const medCd = cooldowns.medkit || 0;
    addButton(
      medCd > 0 ? `Расходник (${medCd}с)` : "Расходник",
      "medkit",
      medCd > 0
    );
  }
}

function updateCore(data, message) {
  if (!authToken) {
    return;
  }
  currentState = data;
  const user = data.user || {};
  const displayName =
    data.display_name ||
    user.first_name ||
    user.username ||
    user.id ||
    "—";
  userLine.textContent = `Пилот: ${displayName}`;
  statsBlock.innerHTML = renderStats(data.rating);
  renderSession(data.session);
  renderEvent(data.event);
  renderQuests(data.quests);
  renderSeason(data.season);
  renderOnboarding(data);
  renderAdminFlag(data);
  if (message) {
    logBlock.textContent = message;
  }
  renderActions(data);
}

async function apiPost(url, body) {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    if (res.status === 401) {
      clearAuthToken("Авторизация истекла. Войдите снова.");
    }
    const text = await res.text();
    throw new Error(text || "API error");
  }
  return res.json();
}

async function apiPostRaw(url, body) {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const text = await res.text();
  let data = null;
  if (text) {
    try {
      data = JSON.parse(text);
    } catch (e) {
      data = null;
    }
  }
  return { ok: res.ok, status: res.status, text, data };
}

if (loginForm) {
  loginForm.onsubmit = async (e) => {
    e.preventDefault();
    const email = loginEmail?.value || "";
    const password = loginPassword?.value || "";
    try {
      const res = await apiPost("/api/auth/login", { email, password });
      if (res.ok && res.token) {
        setAuthToken(res.token, res.user);
        await refreshCore();
      } else {
        loginStatus.textContent = res.message || "Ошибка входа.";
      }
    } catch (err) {
      loginStatus.textContent = "Ошибка входа.";
    }
  };
}

if (registerForm) {
  registerForm.onsubmit = async (e) => {
    e.preventDefault();
    const email = registerEmail?.value || "";
    const nickname = registerNickname?.value || "";
    const password = registerPassword?.value || "";
    try {
      const res = await apiPost("/api/auth/register", {
        email,
        nickname,
        password,
      });
      if (res.ok && res.token) {
        setAuthToken(res.token, res.user);
        await refreshCore();
      } else {
        loginStatus.textContent = res.message || "Ошибка регистрации.";
      }
    } catch (err) {
      loginStatus.textContent = "Ошибка регистрации.";
    }
  };
}


async function refreshCore() {
  if (!hasAuth()) return;
  const data = await apiPost("/api/state", statePayload);
  updateCore(data);
}

async function refreshStorage() {
  const res = await apiPost("/api/storage", {
    ...statePayload,
    page: storageState.page,
    sort: storageState.sort,
  });
  if (res.storage) {
    storageState.page = res.storage.page;
    storageState.sort = res.storage.sort;
    renderStorage(res.storage);
  }
}

async function refreshSell() {
  const res = await apiPost("/api/sell", {
    ...statePayload,
    page: sellState.page,
    sort: sellState.sort,
  });
  if (res.sell) {
    sellState.page = res.sell.page;
    sellState.sort = res.sell.sort;
    renderSell(res.sell);
  }
}

async function refreshShop() {
  const res = await apiPost("/api/shop", statePayload);
  if (!res.shop) return;
  const shop = res.shop;
  shopMeta.innerHTML = `
    <div>Очки <span>${shop.points}</span></div>
    <div>RC <span>${shop.raidcoins}</span></div>
    <div>Слоты <span>${shop.storage_limit}</span></div>
    <div>Страховки <span>${shop.insurance}</span></div>
    <div>Покупки <span>${shop.purchases_today}/${shop.daily_limit}</span></div>
    <div>Налог <span>+${shop.tax_pct}%</span></div>
  `;
  shopStatic.innerHTML = shop.static_items
    .map(
      (item) => {
        const disabled = !item.available || shop.limit_reached;
        return `
      <div class="list-item">
        <div class="item-main">
          <div>${item.label}</div>
          <div class="muted">${item.price} RC</div>
        </div>
        <div class="item-actions">
          <button class="btn buy-btn" data-kind="${item.kind}" ${disabled ? "disabled" : ""}>Купить</button>
        </div>
      </div>
    `;
      }
    )
    .join("");
  shopOffers.innerHTML = shop.offers.length
    ? shop.offers
        .map(
          (offer) => `
        <div class="list-item">
          <div class="item-main">
            <div>${offer.label}</div>
            <div class="muted">${offer.price} очк.</div>
          </div>
          <div class="item-actions">
            <button class="btn buy-offer" data-item="${offer.item_id}" ${shop.limit_reached ? "disabled" : ""}>Купить</button>
          </div>
        </div>
      `
        )
        .join("")
    : "<div class='muted'>Витрина пуста.</div>";
  shopRecipe.innerHTML = "";
  if (shop.recipe_offer) {
    const recipe = shop.recipe_offer;
    const disabled = recipe.owned || shop.limit_reached;
    shopRecipe.innerHTML = `
      <div class="list-item">
        <div class="item-main">
          <div>Рецепт: ${recipe.name}</div>
          <div class="muted">${recipe.price} очк.${recipe.owned ? " • уже изучен" : ""}</div>
        </div>
        <div class="item-actions">
          <button class="btn buy-recipe" data-recipe="${recipe.recipe_id}" ${
            disabled ? "disabled" : ""
          }>Купить</button>
        </div>
      </div>
    `;
  }
  const upgradeDisabled = !shop.upgrade.can_upgrade || shop.points < shop.upgrade.cost;
  shopUpgrade.innerHTML = `
    <div class="list-item">
      <div class="item-main">
        <div>Улучшить склад</div>
        <div class="muted">${shop.upgrade.cost} очк.</div>
      </div>
      <div class="item-actions">
        <button class="btn buy-upgrade" ${upgradeDisabled ? "disabled" : ""}>Улучшить</button>
      </div>
    </div>
  `;
  shopNotice.textContent = res.message || "";

  shopStatic.querySelectorAll(".buy-btn").forEach((btn) => {
    btn.onclick = async () => {
      const kind = btn.dataset.kind;
      const result = await apiPost("/api/shop/buy", { ...statePayload, kind });
      shopNotice.textContent = result.message || "";
      if (result.shop) {
        await refreshShop();
        await refreshCore();
      }
    };
  });
  shopOffers.querySelectorAll(".buy-offer").forEach((btn) => {
    btn.onclick = async () => {
      const itemId = btn.dataset.item;
      const result = await apiPost("/api/shop/buy", {
        ...statePayload,
        kind: "offer",
        item_id: itemId,
      });
      shopNotice.textContent = result.message || "";
      if (result.shop) {
        await refreshShop();
        await refreshCore();
      }
    };
  });
  shopRecipe.querySelectorAll(".buy-recipe").forEach((btn) => {
    btn.onclick = async () => {
      const recipeId = btn.dataset.recipe;
      const result = await apiPost("/api/shop/buy", {
        ...statePayload,
        kind: "recipe",
        recipe_id: recipeId,
      });
      shopNotice.textContent = result.message || "";
      if (result.shop) {
        await refreshShop();
        await refreshCore();
        await refreshCraft();
      }
    };
  });
  shopUpgrade.querySelectorAll(".buy-upgrade").forEach((btn) => {
    btn.onclick = async () => {
      const result = await apiPost("/api/shop/buy", {
        ...statePayload,
        kind: "upgrade",
      });
      shopNotice.textContent = result.message || "";
      if (result.shop) {
        await refreshShop();
        await refreshStorage();
        await refreshCore();
      }
    };
  });
}

async function refreshCraft() {
  const res = await apiPost("/api/craft", statePayload);
  if (!res.craft) return;
  craftList.innerHTML = res.craft.recipes
    .map((recipe) => {
      const ingredients = recipe.ingredients
        .map(
          (ing) =>
            `${ing.emoji} ${ing.name} ${ing.have}/${ing.qty}`
        )
        .join(", ");
      return `
        <div class="list-item">
          <div class="item-main">
            <div>${recipe.name}</div>
            <div class="muted">Выход: ${recipe.output.emoji || ""} ${recipe.output.name} x${recipe.output.qty}</div>
            <div class="muted">${ingredients}</div>
          </div>
          <div class="item-actions">
            <button class="btn craft-btn" data-recipe="${recipe.id}" ${
        recipe.craftable ? "" : "disabled"
      }>Скрафтить</button>
          </div>
        </div>
      `;
    })
    .join("");
  craftList.querySelectorAll(".craft-btn").forEach((btn) => {
    btn.onclick = async () => {
      const recipeId = btn.dataset.recipe;
      const result = await apiPost("/api/craft/make", {
        ...statePayload,
        recipe_id: recipeId,
      });
      craftNotice.textContent = result.message || "";
      await refreshCraft();
      await refreshStorage();
      await refreshCore();
    };
  });
}

async function refreshBlueprints(customNotice = "") {
  const res = await apiPost("/api/blueprints", {
    ...statePayload,
    page: blueprintState.page,
  });
  if (!res.blueprints) return;
  const bp = res.blueprints;
  blueprintState.page = bp.page;
  blueprintPage.textContent = `${bp.page}/${bp.total_pages}`;
  if (!bp.items.length) {
    blueprintList.innerHTML = "<div class='muted'>Чертежей нет.</div>";
  } else {
    blueprintList.innerHTML = bp.items
      .map(
        (item) => `
      <div class="list-item">
        <div class="item-main">
          <div>${item.emoji} ${item.name} x${item.qty}</div>
          <div class="muted">${item.unlocked ? "Изучен" : "Не изучен"}</div>
        </div>
        <div class="item-actions">
          <button class="btn blueprint-btn" data-item="${item.id}" ${
            item.unlocked ? "disabled" : ""
          }>Изучить</button>
        </div>
      </div>
    `
      )
      .join("");
  }
  const hint = bp.unsupported
    ? `Есть чертежи без рецептов: ${bp.unsupported}`
    : "";
  blueprintNotice.textContent = customNotice || hint;
  blueprintList.querySelectorAll(".blueprint-btn").forEach((btn) => {
    btn.onclick = async () => {
      const itemId = btn.dataset.item;
      const result = await apiPost("/api/blueprints/study", {
        ...statePayload,
        item_id: itemId,
      });
      await refreshBlueprints(result.message || "");
      await refreshCraft();
      await refreshStorage();
    };
  });
}

async function refreshLoadout() {
  const res = await apiPost("/api/loadout", statePayload);
  if (!res.loadout) return;
  const l = res.loadout;
  function label(item) {
    return item ? `${item.emoji || ""} ${item.name}` : "нет";
  }
  loadoutCurrent.innerHTML = `
    <div>Броня <span>${label(l.armor)}</span></div>
    <div>Оружие <span>${label(l.weapon)}</span></div>
    <div>Расходник <span>${label(l.medkit)}</span></div>
    <div>Аугмент <span>${label(l.chip)}</span></div>
  `;
}

async function refreshLoadoutOptions() {
  if (!loadoutState.equipType) return;
  const res = await apiPost("/api/loadout/options", {
    ...statePayload,
    equip_type: loadoutState.equipType,
    page: loadoutState.page,
  });
  loadoutPage.textContent = `${res.page}/${res.total_pages}`;
  if (!res.options.length) {
    loadoutOptions.innerHTML = "<div class='muted'>Нет подходящих предметов.</div>";
    return;
  }
  loadoutOptions.innerHTML = res.options
    .map(
      (item) => `
      <div class="list-item">
        <div class="item-main">
          <div>${item.emoji} ${item.name} x${item.qty}</div>
        </div>
        <div class="item-actions">
          <button class="btn equip-btn" data-item="${item.id}">Выбрать</button>
        </div>
      </div>
    `
    )
    .join("");
  loadoutOptions.querySelectorAll(".equip-btn").forEach((btn) => {
    btn.onclick = async () => {
      const itemId = btn.dataset.item;
      const result = await apiPost("/api/loadout/set", {
        ...statePayload,
        equip_type: loadoutState.equipType,
        item_id: itemId,
      });
      loadoutNotice.textContent = result.message || "";
      await refreshLoadout();
    };
  });
}

async function refreshWarehouse() {
  const res = await apiPost("/api/warehouse", statePayload);
  if (!res.warehouse) return;
  const w = res.warehouse;
  const leader = w.top_contrib
    ? `${w.top_contrib.name} (${w.top_contrib.value_total})`
    : "—";
  warehouseMeta.innerHTML = `
    <div>Цель <span>${w.total_items}/${w.goal}</span></div>
    <div>Ценность <span>${w.total_value}</span></div>
    <div>Лидер <span>${leader}</span></div>
  `;
  if (w.order) {
    warehouseOrder.innerHTML = `
      <div class="list-item">
        <div class="item-main">
          <div>${w.order.emoji} ${w.order.name}</div>
          <div class="muted">Прогресс: ${w.order.progress}/${w.order.target}</div>
          <div class="muted">Награда: +${w.order.reward} RC, бонус +${w.order.bonus} RC</div>
        </div>
      </div>
    `;
  } else {
    warehouseOrder.innerHTML = "<div class='muted'>Заказ не активен.</div>";
  }
  warehouseTop.innerHTML = w.top_items.length
    ? w.top_items
        .map(
          (item) => `
        <div class="list-item">
          <div class="item-main">
            <div>${item.emoji} ${item.name} x${item.qty}</div>
          </div>
        </div>
      `
        )
        .join("")
    : "<div class='muted'>Склад пуст.</div>";
}

async function refreshRating() {
  const res = await apiPost("/api/rating", statePayload);
  if (!res.rating) return;
  ratingList.innerHTML = res.rating.rows.length
    ? res.rating.rows
        .map(
          (row) => `
      <div class="list-item">
        <div class="item-main">
          <div>#${row.rank} ${row.name}</div>
          <div class="muted">Очки: ${row.points} • Эвак: ${row.extracts} • Килл: ${row.kills} • Смерти: ${row.deaths}</div>
        </div>
      </div>
    `
        )
        .join("")
    : "<div class='muted'>Рейтинг пуст.</div>";
}

async function refreshCase() {
  const res = await apiPost("/api/daily_case", statePayload);
  if (!res.case) return;
  const c = res.case;
  caseMeta.textContent = c.opened
    ? `Кейс уже открыт сегодня.`
    : `Доступно: ${c.items_count} предмета.`;
  caseOpen.disabled = c.opened;
}

async function refreshMarket() {
  const res = await apiPost("/api/market", {
    ...statePayload,
    page: marketState.page,
    items_page: marketState.itemsPage,
    items_sort: marketState.sort,
  });
  if (res.market) {
    marketState.page = res.market.page;
    marketState.itemsPage = res.market.items_page;
    marketState.sort = res.market.items_sort;
    renderMarket(res.market);
  }
}

async function refreshSeason() {
  const res = await apiPost("/api/season", statePayload);
  if (res.season) {
    renderSeason(res.season);
  }
}

async function refreshAdmin() {
  const res = await apiPost("/api/admin/state", statePayload);
  if (!res.ok) {
    if (adminNotice) adminNotice.textContent = res.message || "";
    return;
  }
  const s = res.settings || {};
  if (adminEventBase) adminEventBase.value = s.event_base ?? "";
  if (adminGreedMult) adminGreedMult.value = s.event_greed_mult ?? "";
  if (adminEvacBase) adminEvacBase.value = s.evac_base ?? "";
  if (adminEvacPenalty) adminEvacPenalty.value = s.evac_greed_penalty ?? "";
  if (adminWarehouseGoal) adminWarehouseGoal.value = s.warehouse_goal ?? "";
  if (adminEventGoal) adminEventGoal.value = s.event_week_goal ?? "";
  if (adminSellCap) adminSellCap.value = s.daily_sell_raidcoin_cap ?? "";
  if (adminSellCountCap) adminSellCountCap.value = s.daily_sell_count_cap ?? "";
  if (adminMarketCap) adminMarketCap.value = s.market_listing_cap ?? "";
  if (adminSeason1) adminSeason1.value = s.season_reward_top1 ?? "";
  if (adminSeason2) adminSeason2.value = s.season_reward_top2 ?? "";
  if (adminSeason3) adminSeason3.value = s.season_reward_top3 ?? "";
}

async function openCase() {
  const res = await apiPost("/api/daily_case/open", statePayload);
  caseNotice.textContent = res.message || "";
  if (res.items) {
    caseList.innerHTML = res.items
      .map(
        (item) => `
      <div class="list-item ${item.rare ? "rare" : ""}">
        <div class="item-main">
          <div>${item.emoji} ${item.name}</div>
          <div class="muted">${item.rarity}</div>
        </div>
      </div>
    `
      )
      .join("");
  }
  await refreshCase();
  await refreshStorage();
  await refreshCore();
}

function handleAction(action) {
  if (!hasAuth()) return;
  if (action === "enter") {
    apiPost("/api/raid/enter", statePayload).then((res) => {
      updateCore(res.state || currentState, res.message);
    });
    return;
  }
  apiPost("/api/raid/action", { ...statePayload, action }).then((res) => {
    updateCore(res.state || currentState, res.message);
  });
}

function initTabs() {
  const tabs = document.querySelectorAll(".tab");
  const views = document.querySelectorAll("[data-view]");
  function showTab(name) {
    activeTab = name;
    tabs.forEach((tab) => {
      tab.classList.toggle("active", tab.dataset.tab === name);
    });
    views.forEach((view) => {
      view.classList.toggle("hidden", view.dataset.view !== name);
    });
    if (!hasAuth()) return;
    if (name === "raid") {
      refreshCore();
    } else if (name === "storage") {
      refreshStorage();
      refreshSell();
    } else if (name === "shop") {
      refreshShop();
    } else if (name === "craft") {
      refreshCraft();
      refreshBlueprints();
    } else if (name === "loadout") {
      refreshLoadout();
    } else if (name === "warehouse") {
      refreshWarehouse();
    } else if (name === "quests") {
      refreshCore();
    } else if (name === "market") {
      refreshMarket();
    } else if (name === "rating") {
      refreshRating();
    } else if (name === "season") {
      refreshSeason();
    } else if (name === "case") {
      refreshCase();
    } else if (name === "admin") {
      refreshAdmin();
    }
  }
  tabs.forEach((tab) => {
    tab.onclick = () => showTab(tab.dataset.tab);
  });
  showTab("raid");
}

if (storagePrev) {
  storagePrev.onclick = () => {
    if (storageState.page > 1) {
      storageState.page -= 1;
      refreshStorage();
    }
  };
}

window.onTelegramAuth = async function (user) {
  if (!user) {
    if (loginStatus) loginStatus.textContent = "Ошибка Telegram-входа.";
    return;
  }
  if (loginStatus) {
    const hasHash = Object.prototype.hasOwnProperty.call(user, "hash");
    const authDate = user.auth_date
      ? new Date(Number(user.auth_date) * 1000).toLocaleString()
      : "нет";
    loginStatus.textContent = `Telegram: id=${user.id || "?"}, hash=${
      hasHash ? "ok" : "нет"
    }, auth_date=${authDate}`;
  }
  if (tgAuthTimer) {
    clearTimeout(tgAuthTimer);
    tgAuthTimer = null;
  }
  try {
    const res = await apiPost("/api/auth/telegram", { login_data: user });
    if (res.ok && res.token) {
      setAuthToken(res.token, res.user);
      await refreshCore();
    } else if (loginStatus) {
      loginStatus.textContent = res.message || "Ошибка Telegram-входа.";
    }
  } catch (err) {
    if (loginStatus) loginStatus.textContent = "Ошибка Telegram-входа.";
  }
};

if (tgLoginWrap) {
  tgLoginWrap.addEventListener("click", () => {
    if (loginStatus) {
      loginStatus.textContent = "Ожидаем авторизацию Telegram...";
    }
    if (tgAuthTimer) {
      clearTimeout(tgAuthTimer);
    }
    tgAuthTimer = setTimeout(() => {
      if (!authToken && loginStatus) {
        loginStatus.textContent =
          "Telegram не вернул данные. Проверьте /setdomain, BOT_TOKEN, WEBAPP_BOT_USERNAME и HTTPS-домен.";
      }
    }, 8000);
  });
}
if (storageNext) {
  storageNext.onclick = () => {
    storageState.page += 1;
    refreshStorage();
  };
}
if (storageUpgrade) {
  storageUpgrade.onclick = async () => {
    const res = await apiPost("/api/storage/upgrade", statePayload);
    storageNotice.textContent = res.message || "";
    if (res.storage) {
      renderStorage(res.storage);
      await refreshCore();
    }
  };
}

document.querySelectorAll(".chip").forEach((chip) => {
  chip.onclick = () => {
    storageState.sort = chip.dataset.sort;
    storageState.page = 1;
    refreshStorage();
  };
});

if (storageSearch) {
  storageSearch.oninput = () => {
    refreshStorage();
  };
}

if (loginBtn) {
  loginBtn.onclick = () => {
    if (loginCard) {
      loginCard.classList.remove("hidden");
      loginCard.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  };
}

if (logoutBtn) {
  logoutBtn.onclick = () => {
    clearAuthToken("Вы вышли из аккаунта.");
    currentState = null;
    renderActions(null);
  };
}

if (sellPrev) {
  sellPrev.onclick = () => {
    if (sellState.page > 1) {
      sellState.page -= 1;
      refreshSell();
    }
  };
}
if (sellNext) {
  sellNext.onclick = () => {
    sellState.page += 1;
    refreshSell();
  };
}
document.querySelectorAll("[data-sell]").forEach((btn) => {
  btn.onclick = async () => {
    if (!sellState.selected) {
      sellNotice.textContent = "Сначала выберите предмет.";
      return;
    }
    const qtyRaw = btn.dataset.sell;
    const res = await apiPost("/api/sell/confirm", {
      ...statePayload,
      item_id: sellState.selected.id,
      qty_raw: qtyRaw,
      page: sellState.page,
      sort: sellState.sort,
    });
    sellNotice.textContent = res.message || "";
    if (res.sell) {
      renderSell(res.sell);
      await refreshCore();
    }
  };
});

if (marketItemsPrev) {
  marketItemsPrev.onclick = () => {
    if (marketState.itemsPage > 1) {
      marketState.itemsPage -= 1;
      refreshMarket();
    }
  };
}
if (marketItemsNext) {
  marketItemsNext.onclick = () => {
    marketState.itemsPage += 1;
    refreshMarket();
  };
}
if (marketPrev) {
  marketPrev.onclick = () => {
    if (marketState.page > 1) {
      marketState.page -= 1;
      refreshMarket();
    }
  };
}
if (marketNext) {
  marketNext.onclick = () => {
    marketState.page += 1;
    refreshMarket();
  };
}

document.querySelectorAll("[data-market-qty]").forEach((btn) => {
  btn.onclick = async () => {
    if (!marketState.selected) {
      marketNotice.textContent = "Сначала выберите предмет.";
      return;
    }
    const qtyRaw = btn.dataset.marketQty;
    const price = Number(marketPrice?.value || 0);
    const res = await apiPost("/api/market/list", {
      ...statePayload,
      item_id: marketState.selected.id,
      qty_raw: qtyRaw,
      price,
    });
    marketNotice.textContent = res.message || "";
    if (res.market) {
      renderMarket(res.market);
      await refreshCore();
    }
  };
});

if (blueprintPrev) {
  blueprintPrev.onclick = () => {
    if (blueprintState.page > 1) {
      blueprintState.page -= 1;
      refreshBlueprints();
    }
  };
}
if (blueprintNext) {
  blueprintNext.onclick = () => {
    blueprintState.page += 1;
    refreshBlueprints();
  };
}

if (loadoutPrev) {
  loadoutPrev.onclick = () => {
    if (loadoutState.page > 1) {
      loadoutState.page -= 1;
      refreshLoadoutOptions();
    }
  };
}
if (loadoutNext) {
  loadoutNext.onclick = () => {
    loadoutState.page += 1;
    refreshLoadoutOptions();
  };
}

document.querySelectorAll("[data-equip]").forEach((btn) => {
  btn.onclick = async () => {
    const type = btn.dataset.equip;
    if (type === "clear") {
      if (!loadoutState.equipType) {
        loadoutNotice.textContent = "Сначала выберите слот.";
        return;
      }
      const res = await apiPost("/api/loadout/set", {
        ...statePayload,
        equip_type: loadoutState.equipType,
        item_id: null,
      });
      loadoutNotice.textContent = res.message || "";
      await refreshLoadout();
      return;
    }
    loadoutState.equipType = type;
    loadoutState.page = 1;
    await refreshLoadoutOptions();
  };
});

if (caseOpen) {
  caseOpen.onclick = () => {
    openCase();
  };
}

if (adminSave) {
  adminSave.onclick = async (e) => {
    e.preventDefault();
    const payload = {
      ...statePayload,
      event_base: Number(adminEventBase?.value || 0),
      event_greed_mult: Number(adminGreedMult?.value || 0),
      evac_base: Number(adminEvacBase?.value || 0),
      evac_greed_penalty: Number(adminEvacPenalty?.value || 0),
      warehouse_goal: Number(adminWarehouseGoal?.value || 0),
      event_week_goal: Number(adminEventGoal?.value || 0),
      daily_sell_raidcoin_cap: Number(adminSellCap?.value || 0),
      daily_sell_count_cap: Number(adminSellCountCap?.value || 0),
      market_listing_cap: Number(adminMarketCap?.value || 0),
      season_reward_top1: Number(adminSeason1?.value || 0),
      season_reward_top2: Number(adminSeason2?.value || 0),
      season_reward_top3: Number(adminSeason3?.value || 0),
    };
    const res = await apiPost("/api/admin/update", payload);
    if (adminNotice) adminNotice.textContent = res.message || "";
    await refreshCore();
  };
}

if (onboardingDone) {
  onboardingDone.onclick = async () => {
    await apiPost("/api/onboarding/complete", statePayload);
    if (onboardingModal) onboardingModal.classList.add("hidden");
    await refreshCore();
  };
}

if (!hasAuth()) {
  userLine.textContent = "Нужен вход по почте.";
  renderActions(null);
  toggleAppButtons(true);
}
initTabs();

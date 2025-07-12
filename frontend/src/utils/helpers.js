/**
 * Format date to Russian locale
 */
export const formatDate = (dateString) => {
  const date = new Date(dateString);
  return date.toLocaleDateString('ru-RU', {
    day: 'numeric',
    month: 'long',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit'
  });
};

/**
 * Format number with spaces as thousands separator
 */
export const formatNumber = (num) => {
  return num.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ' ');
};

/**
 * Get medal emoji by position
 */
export const getMedalEmoji = (position) => {
  const medals = {
    1: '🥇',
    2: '🥈',
    3: '🥉'
  };
  return medals[position] || '🏅';
};

/**
 * Validate Telegram username
 */
export const isValidUsername = (username) => {
  if (!username) return false;
  return /^[a-zA-Z0-9_]{5,32}$/.test(username);
};

/**
 * Get time until date
 */
export const getTimeUntil = (dateString) => {
  const now = new Date();
  const target = new Date(dateString);
  const diff = target - now;
  
  if (diff <= 0) return null;
  
  const days = Math.floor(diff / (1000 * 60 * 60 * 24));
  const hours = Math.floor((diff % (1000 * 60 * 60 * 24)) / (1000 * 60 * 60));
  const minutes = Math.floor((diff % (1000 * 60 * 60)) / (1000 * 60));
  const seconds = Math.floor((diff % (1000 * 60)) / 1000);
  
  return { days, hours, minutes, seconds };
};

/**
 * Get Telegram theme
 */
export const getTelegramTheme = () => {
  if (window.Telegram?.WebApp?.themeParams) {
    return window.Telegram.WebApp.themeParams;
  }
  return {
    bg_color: '#ffffff',
    text_color: '#000000',
    hint_color: '#999999',
    link_color: '#0088cc',
    button_color: '#0088cc',
    button_text_color: '#ffffff',
    secondary_bg_color: '#f0f0f0'
  };
};

/**
 * Show Telegram popup
 */
export const showPopup = (title, message, buttons = []) => {
  if (window.Telegram?.WebApp?.showPopup) {
    return window.Telegram.WebApp.showPopup({
      title,
      message,
      buttons: buttons.length > 0 ? buttons : [{ type: 'ok' }]
    });
  } else {
    alert(`${title}\n\n${message}`);
  }
};

/**
 * Haptic feedback
 */
export const hapticFeedback = (type = 'impact', style = 'light') => {
  if (window.Telegram?.WebApp?.HapticFeedback) {
    const feedback = window.Telegram.WebApp.HapticFeedback;
    
    switch (type) {
      case 'impact':
        feedback.impactOccurred(style);
        break;
      case 'notification':
        feedback.notificationOccurred(style);
        break;
      case 'selection':
        feedback.selectionChanged();
        break;
      default:
        break;
    }
  }
};

/**
 * Open link
 */
export const openLink = (url, options = {}) => {
  if (window.Telegram?.WebApp?.openLink) {
    window.Telegram.WebApp.openLink(url, options);
  } else {
    window.open(url, '_blank');
  }
};

/**
 * Check if running in Telegram
 */
export const isInTelegram = () => {
  return window.Telegram?.WebApp?.initData !== '';
};

/**
 * Get init data
 */
export const getInitData = () => {
  return window.Telegram?.WebApp?.initData || '';
};

/**
 * Get user info from Telegram
 */
export const getTelegramUser = () => {
  return window.Telegram?.WebApp?.initDataUnsafe?.user || null;
};
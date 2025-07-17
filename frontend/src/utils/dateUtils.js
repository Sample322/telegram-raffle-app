/**
 * Форматирование даты в московское время
 */
export const formatToMoscowTime = (dateString) => {
  const date = new Date(dateString);
  
  // Опции для форматирования в московской тайм-зоне
  const options = {
    timeZone: 'Europe/Moscow',
    year: 'numeric',
    month: 'long',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit'
  };
  
  return new Intl.DateTimeFormat('ru-RU', options).format(date);
};

/**
 * Получить московское время для input datetime-local
 */
export const getMoscowTimeForInput = (date = new Date()) => {
  // Конвертируем в московское время
  const moscowTime = new Date(date.toLocaleString("en-US", { timeZone: "Europe/Moscow" }));
  
  // Форматируем для input
  const year = moscowTime.getFullYear();
  const month = String(moscowTime.getMonth() + 1).padStart(2, '0');
  const day = String(moscowTime.getDate()).padStart(2, '0');
  const hours = String(moscowTime.getHours()).padStart(2, '0');
  const minutes = String(moscowTime.getMinutes()).padStart(2, '0');
  
  return `${year}-${month}-${day}T${hours}:${minutes}`;
};

/**
 * Проверить, что дата в будущем (по московскому времени)
 */
export const isFutureMoscowTime = (dateString) => {
  const inputDate = new Date(dateString);
  const nowMoscow = new Date(new Date().toLocaleString("en-US", { timeZone: "Europe/Moscow" }));
  
  return inputDate > nowMoscow;
};
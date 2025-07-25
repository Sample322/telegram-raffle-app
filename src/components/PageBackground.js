import React from 'react';
import '../styles/backgrounds.css';

const PageBackground = ({ page, children }) => {
  // Мапинг страниц к изображениям
  const backgroundImages = {
    home: '/backgrounds/home-bg.jpg',
    raffle: '/backgrounds/raffle-bg.jpg',
    live: '/backgrounds/live-bg.jpg',
    admin: '/backgrounds/admin-bg.jpg',
    default: '/backgrounds/default-bg.jpg'
  };

  const backgroundImage = backgroundImages[page] || backgroundImages.default;

  // Проверяем существование изображения
  const [imageExists, setImageExists] = React.useState(true);

  React.useEffect(() => {
    const img = new Image();
    img.onload = () => setImageExists(true);
    img.onerror = () => setImageExists(false);
    img.src = backgroundImage;
  }, [backgroundImage]);

  const pageClass = `${page}-page`;

  return (
    <div className={pageClass}>
      {imageExists ? (
        <>
          <div 
            className="page-background" 
            style={{ 
              backgroundImage: `url(${backgroundImage})`,
              backgroundColor: `var(--bg-color)`
            }}
          />
          <div className="page-overlay" />
        </>
      ) : (
        <div 
          className="page-background" 
          style={{ backgroundColor: `var(--bg-color)` }}
        />
      )}
      <div className="relative z-10">
        {children}
      </div>
    </div>
  );
};

export default PageBackground;
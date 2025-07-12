import React, { useEffect, useRef } from 'react';

const WheelComponent = ({ participants, isSpinning, onComplete }) => {
  const canvasRef = useRef(null);
  const angleRef = useRef(0);
  const velocityRef = useRef(0);
  const animationRef = useRef(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    const ctx = canvas.getContext('2d');
    
    // Set canvas size
    canvas.width = 500;
    canvas.height = 500;
    
    drawWheel();
  }, [participants]);

  useEffect(() => {
    if (isSpinning) {
      startSpin();
    }
  }, [isSpinning]);

  const drawWheel = () => {
    const canvas = canvasRef.current;
    const ctx = canvas.getContext('2d');
    const centerX = canvas.width / 2;
    const centerY = canvas.height / 2;
    const radius = 200;

    // Clear canvas
    ctx.clearRect(0, 0, canvas.width, canvas.height);

    // Draw wheel segments
    const segmentAngle = (2 * Math.PI) / participants.length;
    
    participants.forEach((participant, index) => {
      const startAngle = angleRef.current + (index * segmentAngle);
      const endAngle = startAngle + segmentAngle;
      
      // Draw segment
      ctx.beginPath();
      ctx.moveTo(centerX, centerY);
      ctx.arc(centerX, centerY, radius, startAngle, endAngle);
      ctx.closePath();
      
      // Alternate colors
      ctx.fillStyle = index % 2 === 0 ? '#3B82F6' : '#8B5CF6';
      ctx.fill();
      
      // Draw border
      ctx.strokeStyle = '#fff';
      ctx.lineWidth = 3;
      ctx.stroke();
      
      // Draw text
      ctx.save();
      ctx.translate(centerX, centerY);
      ctx.rotate(startAngle + segmentAngle / 2);
      ctx.textAlign = 'center';
      ctx.fillStyle = '#fff';
      ctx.font = 'bold 14px Arial';
      ctx.fillText(participant.username, radius * 0.7, 0);
      ctx.restore();
    });

    // Draw center circle
    ctx.beginPath();
    ctx.arc(centerX, centerY, 30, 0, 2 * Math.PI);
    ctx.fillStyle = '#1F2937';
    ctx.fill();

    // Draw pointer
    ctx.beginPath();
    ctx.moveTo(centerX - 20, 50);
    ctx.lineTo(centerX + 20, 50);
    ctx.lineTo(centerX, 80);
    ctx.closePath();
    ctx.fillStyle = '#EF4444';
    ctx.fill();
  };

  const startSpin = () => {
    velocityRef.current = 20 + Math.random() * 10; // Random initial velocity
    animate();
  };

  const animate = () => {
    angleRef.current += velocityRef.current * 0.01;
    velocityRef.current *= 0.985; // Deceleration

    drawWheel();

    if (velocityRef.current > 0.1) {
      animationRef.current = requestAnimationFrame(animate);
    } else {
      // Animation complete
      const selectedIndex = Math.floor(
        ((2 * Math.PI - (angleRef.current % (2 * Math.PI))) / (2 * Math.PI)) * participants.length
      ) % participants.length;
      
      onComplete(participants[selectedIndex]);
    }
  };

  return (
    <div className="relative">
      <canvas ref={canvasRef} className="mx-auto" />
      <div className="absolute top-0 left-1/2 transform -translate-x-1/2 bg-gray-800 text-white px-4 py-2 rounded-lg">
        <p className="text-sm font-semibold">
          {isSpinning ? 'Вращается...' : 'Ожидание...'}
        </p>
      </div>
    </div>
  );
};

export default WheelComponent;
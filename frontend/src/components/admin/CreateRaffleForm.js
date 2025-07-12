import React, { useState } from 'react';
import { toast } from 'react-hot-toast';
import { PlusIcon, TrashIcon } from '@heroicons/react/24/outline';
import api from '../../services/api';

const CreateRaffleForm = ({ onSuccess }) => {
  const [formData, setFormData] = useState({
    title: '',
    description: '',
    photo_url: '',
    channels: [''],
    prizes: { 1: '' },
    end_date: '',
    draw_delay_minutes: 5
  });
  const [uploading, setUploading] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  const handleInputChange = (e) => {
    const { name, value } = e.target;
    setFormData(prev => ({
      ...prev,
      [name]: value
    }));
  };

  const handleChannelChange = (index, value) => {
    const newChannels = [...formData.channels];
    newChannels[index] = value;
    setFormData(prev => ({
      ...prev,
      channels: newChannels
    }));
  };

  const addChannel = () => {
    setFormData(prev => ({
      ...prev,
      channels: [...prev.channels, '']
    }));
  };

  const removeChannel = (index) => {
    const newChannels = formData.channels.filter((_, i) => i !== index);
    setFormData(prev => ({
      ...prev,
      channels: newChannels
    }));
  };

  const handlePrizeChange = (position, value) => {
    setFormData(prev => ({
      ...prev,
      prizes: {
        ...prev.prizes,
        [position]: value
      }
    }));
  };

  const addPrize = () => {
    const positions = Object.keys(formData.prizes).map(Number);
    const nextPosition = Math.max(...positions) + 1;
    setFormData(prev => ({
      ...prev,
      prizes: {
        ...prev.prizes,
        [nextPosition]: ''
      }
    }));
  };

  const removePrize = (position) => {
    const newPrizes = { ...formData.prizes };
    delete newPrizes[position];
    setFormData(prev => ({
      ...prev,
      prizes: newPrizes
    }));
  };

  const handleImageUpload = async (e) => {
    const file = e.target.files[0];
    if (!file) return;

    if (!file.type.startsWith('image/')) {
      toast.error('Пожалуйста, выберите изображение');
      return;
    }

    setUploading(true);
    const formData = new FormData();
    formData.append('file', file);

    try {
      const response = await api.post('/admin/upload-image', formData, {
        headers: {
          'Content-Type': 'multipart/form-data'
        }
      });
      setFormData(prev => ({
        ...prev,
        photo_url: response.data.url
      }));
      toast.success('Изображение загружено');
    } catch (error) {
      toast.error('Ошибка загрузки изображения');
    } finally {
      setUploading(false);
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    
    // Validation
    if (!formData.title || !formData.description) {
      toast.error('Заполните все обязательные поля');
      return;
    }

    const validChannels = formData.channels.filter(ch => ch.trim());
    const validPrizes = Object.fromEntries(
      Object.entries(formData.prizes).filter(([_, prize]) => prize.trim())
    );

    if (Object.keys(validPrizes).length === 0) {
      toast.error('Добавьте хотя бы один приз');
      return;
    }

    setSubmitting(true);

    try {
      const payload = {
        ...formData,
        channels: validChannels,
        prizes: validPrizes,
        end_date: new Date(formData.end_date).toISOString()
      };

      await api.post('/admin/raffles', payload);
      toast.success('Розыгрыш успешно создан!');
      
      // Reset form
      setFormData({
        title: '',
        description: '',
        photo_url: '',
        channels: [''],
        prizes: { 1: '' },
        end_date: '',
        draw_delay_minutes: 5
      });

      if (onSuccess) {
        onSuccess();
      }
    } catch (error) {
      toast.error('Ошибка создания розыгрыша');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="bg-white rounded-lg shadow-lg p-6">
      <h2 className="text-2xl font-semibold mb-6">Создать новый розыгрыш</h2>
      
      {/* Title */}
      <div className="mb-4">
        <label className="block text-gray-700 text-sm font-bold mb-2">
          Название розыгрыша *
        </label>
        <input
          type="text"
          name="title"
          value={formData.title}
          onChange={handleInputChange}
          className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:border-blue-500"
          required
        />
      </div>

      {/* Description */}
      <div className="mb-4">
        <label className="block text-gray-700 text-sm font-bold mb-2">
          Описание *
        </label>
        <textarea
          name="description"
          value={formData.description}
          onChange={handleInputChange}
          rows="4"
          className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:border-blue-500"
          required
        />
      </div>

      {/* Image Upload */}
      <div className="mb-4">
        <label className="block text-gray-700 text-sm font-bold mb-2">
          Изображение
        </label>
        <input
          type="file"
          accept="image/*"
          onChange={handleImageUpload}
          disabled={uploading}
          className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:border-blue-500"
        />
        {uploading && <p className="text-sm text-gray-500 mt-1">Загрузка...</p>}
        {formData.photo_url && (
          <img 
            src={formData.photo_url} 
            alt="Preview" 
            className="mt-2 h-32 object-cover rounded"
          />
        )}
      </div>

      {/* Channels */}
      <div className="mb-4">
        <label className="block text-gray-700 text-sm font-bold mb-2">
          Каналы для подписки
        </label>
        {formData.channels.map((channel, index) => (
          <div key={index} className="flex mb-2">
            <input
              type="text"
              value={channel}
              onChange={(e) => handleChannelChange(index, e.target.value)}
              placeholder="@channel_username"
              className="flex-1 px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:border-blue-500"
            />
            <button
              type="button"
              onClick={() => removeChannel(index)}
              className="ml-2 text-red-600 hover:text-red-800"
            >
              <TrashIcon className="h-5 w-5" />
            </button>
          </div>
        ))}
        <button
          type="button"
          onClick={addChannel}
          className="mt-2 flex items-center text-blue-600 hover:text-blue-800"
        >
          <PlusIcon className="h-5 w-5 mr-1" />
          Добавить канал
        </button>
      </div>

      {/* Prizes */}
      <div className="mb-4">
        <label className="block text-gray-700 text-sm font-bold mb-2">
          Призы *
        </label>
        {Object.entries(formData.prizes).map(([position, prize]) => (
          <div key={position} className="flex mb-2">
            <span className="flex items-center px-3 bg-gray-100 border border-r-0 border-gray-300 rounded-l-lg">
              {position} место
            </span>
            <input
              type="text"
              value={prize}
              onChange={(e) => handlePrizeChange(position, e.target.value)}
              placeholder="Название приза"
              className="flex-1 px-3 py-2 border border-gray-300 rounded-r-lg focus:outline-none focus:border-blue-500"
            />
            {Object.keys(formData.prizes).length > 1 && (
              <button
                type="button"
                onClick={() => removePrize(position)}
                className="ml-2 text-red-600 hover:text-red-800"
              >
                <TrashIcon className="h-5 w-5" />
              </button>
            )}
          </div>
        ))}
        <button
          type="button"
          onClick={addPrize}
          className="mt-2 flex items-center text-blue-600 hover:text-blue-800"
        >
          <PlusIcon className="h-5 w-5 mr-1" />
          Добавить приз
        </button>
      </div>

      {/* End Date */}
      <div className="mb-4">
        <label className="block text-gray-700 text-sm font-bold mb-2">
          Дата и время окончания *
        </label>
        <input
          type="datetime-local"
          name="end_date"
          value={formData.end_date}
          onChange={handleInputChange}
          className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:border-blue-500"
          required
        />
      </div>

      {/* Draw Delay */}
      <div className="mb-6">
        <label className="block text-gray-700 text-sm font-bold mb-2">
          Задержка перед началом розыгрыша (минут)
        </label>
        <input
          type="number"
          name="draw_delay_minutes"
          value={formData.draw_delay_minutes}
          onChange={handleInputChange}
          min="1"
          max="60"
          className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:border-blue-500"
        />
      </div>

      {/* Submit Button */}
      <button
        type="submit"
        disabled={submitting}
        className="w-full bg-blue-600 text-white py-3 px-4 rounded-lg font-semibold hover:bg-blue-700 transition-colors duration-200 disabled:opacity-50 disabled:cursor-not-allowed"
      >
        {submitting ? 'Создание...' : 'Создать розыгрыш'}
      </button>
    </form>
  );
};

export default CreateRaffleForm;
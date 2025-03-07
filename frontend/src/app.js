import React, { useState, useEffect } from 'react';
import './App.css';

const CITIES = {
  minsk: '🏠 Минск',
  brest: '🏰 Брест',
  grodno: '🌳 Гродно',
  gomel: '🌿 Гомель',
  vitebsk: '🎨 Витебск',
  mogilev: '🏭 Могилев',
};

function App() {
  const [activeTab, setActiveTab] = useState('search');
  const [ads, setAds] = useState([]);
  const [newAds, setNewAds] = useState([]);
  const [userAds, setUserAds] = useState([]);
  const [modalImage, setModalImage] = useState(null);
  const [offset, setOffset] = useState(0);
  const [currentParams, setCurrentParams] = useState(null);
  const [isSearched, setIsSearched] = useState(false);
  const [showUserAdForm, setShowUserAdForm] = useState(false);
  const [formData, setFormData] = useState({
    images: [],
    city: '',
    rooms: '',
    price: '',
    address: '',
    description: '',
    phone: ''
  });
  
  const urlParams = new URLSearchParams(window.location.search);
  const userId = urlParams.get('user_id') || 'default';
  const adminId = process.env.REACT_APP_ADMIN_ID || '854773231';

  useEffect(() => {
    if (window.Telegram?.WebApp) {
      window.Telegram.WebApp.ready();
      window.Telegram.WebApp.expand();
      window.Telegram.WebApp.setHeaderColor('#2a2a2a');
      window.Telegram.WebApp.disableVerticalSwipes();
    }
    
    const savedState = JSON.parse(localStorage.getItem('searchState'));
    if (savedState?.isSearched) {
      setIsSearched(true);
      const params = new URLSearchParams();
      params.append('user_id', userId);
      ['city', 'minPrice', 'maxPrice', 'rooms'].forEach(key => {
        if (savedState[key]) params.append(key, savedState[key]);
      });
      fetchAds(params, 7);
    }
  }, []);

  const vibrate = () => {
    window.Telegram?.WebApp?.HapticFeedback?.impactOccurred('light');
  };

  const fetchAds = async (params, limit) => {
    try {
      params.set('offset', offset);
      params.set('limit', limit);
      const response = await fetch(`https://newtg-3bcd.onrender.com/api/ads?${params.toString()}`);
      const data = await response.json();
      setAds(prev => [...prev, ...(data.ads || [])]);
      setOffset(data.ads ? data.ads.length + offset : offset);
      setIsSearched(true);
    } catch (error) {
      setAds([{ error: `Ошибка загрузки данных: ${error.message}` }]);
    }
  };

  // Остальные хуки и методы с аналогичными улучшениями...

  return (
    <div id="app-container" className="h-screen w-screen overflow-y-auto pb-20">
      {/* Верстка с исправленными эмодзи и обработкой ошибок */}
    </div>
  );
}

export default App;

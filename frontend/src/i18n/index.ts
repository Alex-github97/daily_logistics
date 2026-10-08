import i18n from 'i18next'
import { initReactI18next } from 'react-i18next'
import LanguageDetector from 'i18next-browser-languagedetector'

import es from './locales/es.json'
import en from './locales/en.json'
import pt from './locales/pt.json'
import fr from './locales/fr.json'
import de from './locales/de.json'
import zh from './locales/zh.json'
import ja from './locales/ja.json'
import it from './locales/it.json'
import ko from './locales/ko.json'
import ru from './locales/ru.json'

export const SUPPORTED_LANGUAGES = [
  { code: 'es', name: 'Español',    flag: '🇪🇸' },
  { code: 'en', name: 'English',    flag: '🇺🇸' },
  { code: 'pt', name: 'Português',  flag: '🇧🇷' },
  { code: 'fr', name: 'Français',   flag: '🇫🇷' },
  { code: 'de', name: 'Deutsch',    flag: '🇩🇪' },
  { code: 'zh', name: '中文',        flag: '🇨🇳' },
  { code: 'ja', name: '日本語',      flag: '🇯🇵' },
  { code: 'it', name: 'Italiano',   flag: '🇮🇹' },
  { code: 'ko', name: '한국어',      flag: '🇰🇷' },
  { code: 'ru', name: 'Русский',    flag: '🇷🇺' },
]

i18n
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    resources: { es, en, pt, fr, de, zh, ja, it, ko, ru },
    fallbackLng: 'es',
    defaultNS: 'translation',
    detection: {
      order: ['localStorage', 'navigator'],
      lookupLocalStorage: 'empresa_lang',
      caches: ['localStorage'],
    },
    interpolation: { escapeValue: false },
  })

export default i18n

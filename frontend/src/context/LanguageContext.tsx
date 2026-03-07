import React, { createContext, useContext, useState, useEffect, ReactNode } from 'react';
import { Language, t as translate, getSavedLanguage, saveLanguage } from '../i18n';

interface LangContextType {
  language: Language;
  setLang: (lang: Language) => void;
  t: (key: string) => string;
}

const LangContext = createContext<LangContextType>({
  language: 'en',
  setLang: () => {},
  t: (key) => key,
});

export const useLang = () => useContext(LangContext);

export function LanguageProvider({ children }: { children: ReactNode }) {
  const [language, setLanguage] = useState<Language>('en');

  useEffect(() => {
    getSavedLanguage().then(setLanguage);
  }, []);

  const setLang = (lang: Language) => {
    setLanguage(lang);
    saveLanguage(lang);
  };

  const t = (key: string) => translate(key, language);

  return (
    <LangContext.Provider value={{ language, setLang, t }}>
      {children}
    </LangContext.Provider>
  );
}

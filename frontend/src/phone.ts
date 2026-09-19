import { parsePhoneNumberFromString, AsYouType, CountryCode } from 'libphonenumber-js';

/** Countries the business serves. India is the default everywhere; USA and Canada share +1, Australia is +61. */
export const COUNTRIES: { code: CountryCode; dial: string; label: string; flag: string; example: string; maxDigits: number }[] = [
  { code: 'IN', dial: '+91', label: 'India', flag: '\u{1F1EE}\u{1F1F3}', example: '98765 43210', maxDigits: 10 },
  { code: 'US', dial: '+1', label: 'USA', flag: '\u{1F1FA}\u{1F1F8}', example: '415 555 2671', maxDigits: 10 },
  { code: 'CA', dial: '+1', label: 'Canada', flag: '\u{1F1E8}\u{1F1E6}', example: '416 555 0134', maxDigits: 10 },
  { code: 'AU', dial: '+61', label: 'Australia', flag: '\u{1F1E6}\u{1F1FA}', example: '412 345 678', maxDigits: 9 },
];
export const DEFAULT_COUNTRY: CountryCode = 'IN';

/**
 * Canonical value sent to the backend: Indian numbers stay the historical 10 national digits (all existing accounts
 * use that form); USA / Canada / Australia are sent in E.164 so they are never truncated or confused with an Indian
 * number. Returns null when the number is not valid for the chosen country.
 */
export function canonicalPhone(national: string, country: CountryCode = DEFAULT_COUNTRY): string | null {
  const digits = national.replace(/\D/g, '');
  if (!digits) return null;
  const parsed = parsePhoneNumberFromString(digits, country);
  if (!parsed || !parsed.isValid() || parsed.country !== country) return null;
  if (country === 'IN') {
    const n = parsed.nationalNumber;
    return /^[6-9][0-9]{9}$/.test(n) ? n : null;
  }
  return parsed.number; // E.164
}

/** Split a stored canonical number back into country + national digits (for edit forms and display). */
export function splitCanonical(value: string): { country: CountryCode; national: string } {
  const text = (value || '').trim();
  if (!text.startsWith('+')) return { country: 'IN', national: text.replace(/\D/g, '').slice(-10) };
  const parsed = parsePhoneNumberFromString(text);
  if (parsed && parsed.country && COUNTRIES.some(c => c.code === parsed.country)) return { country: parsed.country as CountryCode, national: parsed.nationalNumber };
  return { country: 'IN', national: text.replace(/\D/g, '').slice(-10) };
}

/** Human display: "+91 98765 43210", "+1 415 555 2671". */
export function displayPhone(value: string): string {
  const text = (value || '').trim();
  if (!text) return '';
  const parsed = parsePhoneNumberFromString(text.startsWith('+') ? text : `+91${text.replace(/\D/g, '').slice(-10)}`);
  return parsed ? parsed.formatInternational() : text;
}

export function formatAsYouType(national: string, country: CountryCode): string {
  const digits = national.replace(/\D/g, '');
  return new AsYouType(country).input(digits) || digits;
}

export function maskPhone(value: string): string {
  const text = (value || '').trim();
  return text.length > 4 ? '\u2022'.repeat(Math.min(6, text.length - 4)) + text.slice(-4) : '\u2022\u2022\u2022\u2022';
}

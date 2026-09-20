import { parsePhoneNumberFromString, CountryCode } from 'libphonenumber-js';

/** Countries the business serves. India is the default everywhere; USA and Canada share +1, Australia is +61. */
export const COUNTRIES: { code: CountryCode; dial: string; label: string; flag: string; example: string }[] = [
  { code: 'IN', dial: '+91', label: 'India', flag: '\u{1F1EE}\u{1F1F3}', example: '98765 43210' },
  { code: 'US', dial: '+1', label: 'USA', flag: '\u{1F1FA}\u{1F1F8}', example: '415 555 2671' },
  { code: 'CA', dial: '+1', label: 'Canada', flag: '\u{1F1E8}\u{1F1E6}', example: '416 555 0134' },
  { code: 'AU', dial: '+61', label: 'Australia', flag: '\u{1F1E6}\u{1F1FA}', example: '412 345 678' },
];
export const DEFAULT_COUNTRY: CountryCode = 'IN';
const SUPPORTED = new Set<string>(COUNTRIES.map(c => c.code));
/** Longest sensible raw entry (trunk prefix + country code + national digits); nothing shorter is ever cut. */
export const MAX_INPUT_DIGITS = 18;

export const countryMeta = (code: CountryCode) => COUNTRIES.find(c => c.code === code) || COUNTRIES[0];

/** "+…", "00…" and punctuation-tolerant cleanup: keeps a leading plus and every digit, nothing else. */
function clean(raw: string): string {
  let text = (raw || '').replace(/[^\d+]/g, '');
  if (text.startsWith('00')) text = '+' + text.slice(2);
  text = text[0] === '+' ? '+' + text.slice(1).replace(/\+/g, '') : text.replace(/\+/g, '');
  return text;
}

function parseWithin(digits: string, country: CountryCode) {
  const parsed = parsePhoneNumberFromString(digits, country);
  if (parsed && parsed.isValid() && parsed.country && SUPPORTED.has(parsed.country)) return parsed;
  // Digits typed with the country code but without "+", e.g. 91 98765 43210 or 61 412 345 678
  const dial = countryMeta(country).dial.slice(1);
  if (digits.startsWith(dial) && digits.length > dial.length) {
    const intl = parsePhoneNumberFromString('+' + digits);
    if (intl && intl.isValid() && intl.country && SUPPORTED.has(intl.country)) return intl;
  }
  return null;
}

/**
 * Interpret what the user typed or pasted. Formatting, spaces, brackets, dashes, a trunk zero (0412 345 678,
 * 09876 543210) and full international numbers (+1 (415) 555-2671, 0061 412 345 678) are all accepted; digits are
 * never dropped - an over-long or foreign number simply stays invalid until corrected. A pasted international number
 * switches the country selector to the number's own country.
 */
export function parseInput(raw: string, country: CountryCode): { country: CountryCode; national: string } {
  const text = clean(raw);
  if (text.startsWith('+')) {
    const parsed = parsePhoneNumberFromString(text);
    if (parsed && parsed.country && SUPPORTED.has(parsed.country)) return { country: parsed.country as CountryCode, national: parsed.nationalNumber };
    return { country, national: text.slice(1).slice(0, MAX_INPUT_DIGITS) };
  }
  const digits = text.slice(0, MAX_INPUT_DIGITS);
  const parsed = parseWithin(digits, country);
  // +1 is shared: a Canadian area code typed under USA (or the reverse) follows the number, not the selector
  if (parsed && parsed.country && parsed.country !== country) return { country: parsed.country as CountryCode, national: digits };
  return { country, national: digits };
}

/**
 * Canonical value sent to the backend, matching shared/core.py::phone(): Indian numbers stay the historical 10
 * national digits (every existing account uses that form); USA / Canada / Australia travel in E.164 so they are never
 * truncated or confused with an Indian number. Returns null when the entry is not a valid number of the chosen country.
 */
export function canonicalPhone(national: string, country: CountryCode = DEFAULT_COUNTRY): string | null {
  const digits = clean(national).replace(/^\+/, '');
  if (!digits) return null;
  const parsed = parseWithin(digits, country);
  if (!parsed || !parsed.country) return null;
  const sharedDial = countryMeta(parsed.country as CountryCode).dial === countryMeta(country).dial;
  if (parsed.country !== country && !sharedDial) return null;
  if (parsed.country === 'IN') {
    const n = parsed.nationalNumber;
    return /^[6-9][0-9]{9}$/.test(n) ? n : null;
  }
  return parsed.number; // E.164
}

/** Stored canonical / legacy value ("9876543210", "919876543210", "+61412345678") as an E.164 string. */
export function toE164(value: string): string {
  const text = clean(value || '');
  if (!text) return '';
  if (text.startsWith('+')) return text;
  const digits = text.length === 12 && text.startsWith('91') ? text.slice(2) : text;
  return `+91${digits}`;
}

/** Split a stored canonical number back into country + national digits (for edit forms). */
export function splitCanonical(value: string): { country: CountryCode; national: string } {
  const parsed = parsePhoneNumberFromString(toE164(value));
  if (parsed && parsed.country && SUPPORTED.has(parsed.country)) return { country: parsed.country as CountryCode, national: parsed.nationalNumber };
  return { country: DEFAULT_COUNTRY, national: (value || '').replace(/\D/g, '') };
}

/** Human display: "+91 98765 43210", "+1 415 555 2671", "+61 412 345 678". */
export function displayPhone(value: string): string {
  const text = (value || '').trim();
  if (!text) return '';
  const parsed = parsePhoneNumberFromString(toE164(text));
  return parsed ? parsed.formatInternational() : text;
}

/** Contact actions keep the number's own country code: never "91" prepended to a foreign number. */
export const telLink = (value: string) => `tel:${toE164(value)}`;
export const whatsappLink = (value: string, text?: string) =>
  `https://wa.me/${toE164(value).replace(/\D/g, '')}${text ? `?text=${encodeURIComponent(text)}` : ''}`;

export function maskPhone(value: string): string {
  const text = (value || '').trim();
  return text.length > 4 ? '\u2022'.repeat(Math.min(6, text.length - 4)) + text.slice(-4) : '\u2022\u2022\u2022\u2022';
}

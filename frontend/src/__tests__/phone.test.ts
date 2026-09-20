import { canonicalPhone, displayPhone, parseInput, splitCanonical, telLink, toE164, whatsappLink } from '../phone';

describe('international phone parsing (frontend mirrors shared/core.py::phone)', () => {
  it('India (default): 10 national digits, tolerant of trunk zero, 91 prefix, +91 and punctuation', () => {
    expect(canonicalPhone('9876543210', 'IN')).toBe('9876543210');
    expect(canonicalPhone('98765 43210', 'IN')).toBe('9876543210');
    expect(canonicalPhone('09876543210', 'IN')).toBe('9876543210');
    expect(canonicalPhone('919876543210', 'IN')).toBe('9876543210');
    expect(canonicalPhone('+91-98765-43210', 'IN')).toBe('9876543210');
    expect(canonicalPhone('1234567890', 'IN')).toBeNull(); // first digit must be 6-9
    expect(canonicalPhone('98765', 'IN')).toBeNull();
    expect(canonicalPhone('', 'IN')).toBeNull();
  });

  it('USA and Canada share +1 and are sent in E.164; the number decides between the two', () => {
    expect(canonicalPhone('4155552671', 'US')).toBe('+14155552671');
    expect(canonicalPhone('(415) 555-2671', 'US')).toBe('+14155552671');
    expect(canonicalPhone('1 415 555 2671', 'US')).toBe('+14155552671');
    expect(canonicalPhone('4165550134', 'CA')).toBe('+14165550134');
    expect(canonicalPhone('4165550134', 'US')).toBe('+14165550134'); // Toronto area code typed under USA still valid +1
    expect(canonicalPhone('415 555 26', 'US')).toBeNull();
  });

  it('Australia: 9 national digits, leading zero and 0061 accepted, never cut', () => {
    expect(canonicalPhone('412345678', 'AU')).toBe('+61412345678');
    expect(canonicalPhone('0412 345 678', 'AU')).toBe('+61412345678');
    expect(canonicalPhone('0061 412 345 678', 'AU')).toBe('+61412345678');
    expect(canonicalPhone('+61 (0)412-345-678', 'AU')).toBe('+61412345678');
    expect(canonicalPhone('41234567', 'AU')).toBeNull();
  });

  it('a number of another country is invalid for the selected one; unsupported countries are refused', () => {
    expect(canonicalPhone('9876543210', 'AU')).toBeNull();
    expect(canonicalPhone('412345678', 'IN')).toBeNull();
    expect(canonicalPhone('+44 7911 123456', 'IN')).toBeNull();
  });

  it('pasted or formatted input keeps every digit and switches the country for international numbers', () => {
    expect(parseInput('+61 412 345 678', 'IN')).toEqual({ country: 'AU', national: '412345678' });
    expect(parseInput('0061412345678', 'IN')).toEqual({ country: 'AU', national: '412345678' });
    expect(parseInput('+1 (416) 555-0134', 'IN')).toEqual({ country: 'CA', national: '4165550134' });
    expect(parseInput('+1 (415) 555-2671', 'CA')).toEqual({ country: 'US', national: '4155552671' });
    expect(parseInput('+91 98765 43210', 'US')).toEqual({ country: 'IN', national: '9876543210' });
    // national formats are kept as typed (digits only) - the trunk zero is resolved by canonicalPhone, not by cutting
    expect(parseInput('0412 345 678', 'AU')).toEqual({ country: 'AU', national: '0412345678' });
    expect(parseInput('98765-43210', 'IN')).toEqual({ country: 'IN', national: '9876543210' });
    expect(parseInput('4165550134', 'US')).toEqual({ country: 'CA', national: '4165550134' });
    // an unsupported international number is not truncated to 10 digits and stays invalid
    const uk = parseInput('+44 7911 123456', 'IN');
    expect(uk).toEqual({ country: 'IN', national: '447911123456' });
    expect(canonicalPhone(uk.national, uk.country)).toBeNull();
    // over-long garbage is bounded but a valid long entry (trunk + code + number) is kept
    expect(parseInput('0091 98765 43210', 'IN')).toEqual({ country: 'IN', national: '9876543210' });
  });

  it('changing the country re-interprets the digits already typed instead of discarding them', () => {
    const typed = parseInput('412345678', 'IN').national;
    expect(canonicalPhone(typed, 'IN')).toBeNull();
    expect(canonicalPhone(parseInput(typed, 'AU').national, 'AU')).toBe('+61412345678');
  });

  it('display, split and contact links preserve each number\'s own country code', () => {
    expect(displayPhone('9876543210')).toBe('+91 98765 43210');
    expect(displayPhone('919876543210')).toBe('+91 98765 43210');
    expect(displayPhone('+14155552671')).toBe('+1 415 555 2671');
    expect(displayPhone('+61412345678')).toBe('+61 412 345 678');
    expect(splitCanonical('+61412345678')).toEqual({ country: 'AU', national: '412345678' });
    expect(splitCanonical('9876543210')).toEqual({ country: 'IN', national: '9876543210' });
    expect(toE164('9876543210')).toBe('+919876543210');
    expect(telLink('9876543210')).toBe('tel:+919876543210');
    expect(telLink('+61412345678')).toBe('tel:+61412345678');
    expect(whatsappLink('+14155552671')).toBe('https://wa.me/14155552671');
    expect(whatsappLink('9876543210', 'Hi')).toBe('https://wa.me/919876543210?text=Hi');
  });
});

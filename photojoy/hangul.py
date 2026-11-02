"""Small modern Hangul two-set composer for name fields when Windows IME is unavailable.

No global keyboard hooks: only explicit input in PhotoJoy's name/group fields.
"""

INITIAL = 'ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ'
VOWEL = 'ㅏㅐㅑㅒㅓㅔㅕㅖㅗㅘㅙㅚㅛㅜㅝㅞㅟㅠㅡㅢㅣ'
FINAL = ' ㄱㄲㄳㄴㄵㄶㄷㄹㄺㄻㄼㄽㄾㄿㅀㅁㅂㅄㅅㅆㅇㅈㅊㅋㅌㅍㅎ'
KEYS = dict(zip('rsefaqtdwczxvgkoijuphynbml', 'ㄱㄴㄷㄹㅁㅂㅅㅇㅈㅊㅋㅌㅍㅎㅏㅐㅑㅓㅕㅔㅗㅛㅜㅠㅡㅣ'))
KEYS.update(dict(zip('REQTWOP', 'ㄲㄸㅃㅆㅉㅒㅖ')))
JOIN_VOWEL = {'ㅗㅏ':'ㅘ','ㅗㅐ':'ㅙ','ㅗㅣ':'ㅚ','ㅜㅓ':'ㅝ','ㅜㅔ':'ㅞ','ㅜㅣ':'ㅟ','ㅡㅣ':'ㅢ'}
JOIN_FINAL = {'ㄱㅅ':'ㄳ','ㄴㅈ':'ㄵ','ㄴㅎ':'ㄶ','ㄹㄱ':'ㄺ','ㄹㅁ':'ㄻ','ㄹㅂ':'ㄼ','ㄹㅅ':'ㄽ','ㄹㅌ':'ㄾ','ㄹㅍ':'ㄿ','ㄹㅎ':'ㅀ','ㅂㅅ':'ㅄ'}
SPLIT_FINAL = {value: tuple(key) for key,value in JOIN_FINAL.items()}


def compose(keys: str) -> str:
    output = []
    initial = vowel = final = ''

    def current():
        if initial and vowel:
            return chr(0xAC00 + (INITIAL.index(initial)*21 + VOWEL.index(vowel))*28 + (FINAL.index(final) if final else 0))
        return initial or vowel

    for key in keys:
        char = KEYS.get(key, KEYS.get(key.lower(), key))
        if char in INITIAL:
            if initial and vowel:
                if not final and char in FINAL:
                    final = char
                elif final+char in JOIN_FINAL:
                    final = JOIN_FINAL[final+char]
                else:
                    output.append(current()); initial,vowel,final = char,'',''
            else:
                if current(): output.append(current())
                initial,vowel,final = char,'',''
        elif char in VOWEL:
            if initial and vowel and final:
                carry = final
                if final in SPLIT_FINAL:
                    final, carry = SPLIT_FINAL[final]
                else:
                    final = ''
                output.append(current()); initial,vowel,final = carry,char,''
            elif vowel:
                if vowel+char in JOIN_VOWEL:
                    vowel = JOIN_VOWEL[vowel+char]
                else:
                    output.append(current()); initial,vowel,final = '',char,''
            else:
                vowel = char
        else:
            if current(): output.append(current())
            output.append(char); initial=vowel=final=''
    if current(): output.append(current())
    return ''.join(output)

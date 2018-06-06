# -*- coding: utf-8 -*-

def input_valid(text):
    if type(text) is not str:
        return False
    ret = True
    def isletter(a):
        return (ord('a')<=ord(a)<=ord('z')) or (ord('A')<=ord(a)<=ord('Z'))
    def isnumber(a):
        return ord('0')<=ord(a)<=ord('9')
    for i in text:
        if (not isletter(i)) and (not isnumber(i)) and i!='_':
            ret = False
            break
    return ret



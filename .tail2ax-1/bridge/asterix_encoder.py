# -*- coding: utf-8 -*-
import sys
from collections import OrderedDict

import asterix
import lxml.etree as et


class AsterixEncoder:
    def __init__(self):
        self._xml_cache = {}
        self._axmsg = bytearray()

    def encode(self, data):
        self._d = data
        cat = '{:03}'.format(self._d['category'])
        self._check_xml_cache(cat)
        root = self._xml_cache[cat].getroot()

        self._axmsg = bytearray()
        self._axmsg.append(self._d['category'])
        self._axmsg.append(0)
        self._axmsg.append(0)
        self._chunk = OrderedDict()
        self._len = {}
        for child in root:
            if child.tag == 'DataItem':
                self._proc_dataitem(child)
            elif child.tag == 'UAP':
                self._proc_uaps(child)
            else:
                pass
        for k in self._order:
            if k in self._chunk:
                self._axmsg += self._chunk[k]
        _len = len(self._axmsg)
        self._axmsg[1] = int(_len / 256)
        self._axmsg[2] = int(_len % 256)
        return self._axmsg

    def __str__(self):
        return self.format(self._axmsg)

    def format(self, m):
        return "[{}]".format(', '.join(['0x{:02x}'.format(x) for x in m]))

    def print(self, m):
        print(self.format(m))

    def _check_xml_cache(self, cat):
        if cat not in self._xml_cache:
            with open(asterix.get_configuration_file(cat)) as fp:
                self._xml_cache[cat] = et.parse(fp)

    def _proc_dataitem(self, dataitem):
        ch = bytearray()
        _id = 'I{}'.format(dataitem.attrib['id'])
        if _id not in self._d:
            return
        # print(_id)
        for child in dataitem:
            if child.tag == 'DataItemFormat':
                for subchild in child:
                    if subchild.tag == 'Fixed':
                        ch += self._get_fixed(_id, self._d[_id], subchild)
                    elif subchild.tag == 'Variable':
                        if isinstance(self._d[_id], dict):
                            ch += self._get_variable(_id, self._d[_id], subchild)
                        else:
                            b = bytearray()
                            for d in self._d[_id]:
                                b += self._get_variable(_id, d, subchild)
                            if len(b) > 1:
                                for x in range(len(b) - 1):
                                    b[x] |= 0x01
                            ch += b
                    elif subchild.tag == 'Repetitive':
                        ch += self._get_repetitive(_id, subchild)
                    elif subchild.tag == 'Explicit':
                        ch += self._get_explicit(_id, self._d[_id], subchild)
                    elif subchild.tag == 'Compound':
                        ch += self._get_compound(_id, self._d[_id], subchild)
                    elif subchild.tag == 'BSD':
                        ch += self._get_bds(_id, self._d[_id], self._xml_cache['bds'].getroot())
                    else:
                        pass
            else:
                pass

        self._chunk[_id] = ch

    def _proc_uaps(self, uaps):
        self._order = []
        nbits = len(uaps)
        x = 0
        for child in uaps:
            if child.tag == 'UAPItem':
                shift = nbits - 1 - int(child.attrib['bit'])
                if child.attrib['frn'] == 'FX':
                    pass
                else:
                    tag = 'I{}'.format(child.text)
                    self._order.append(tag)
                    if tag in self._d:
                        mask = 1 << shift
                        x |= mask
                        self._len[tag] = child.attrib['len']
        a = bytearray()
        for n in range(int(nbits / 8)):
            if x & 0xff == 0:
                if len(a):
                    a.insert(0, x & 0xff)
                x >>= 8
            else:
                a.insert(0, x & 0xff)
                x >>= 8
        for i in range(len(a) - 1):
            a[i] |= 1
        self._axmsg += a

    def _get_fixed(self, i, data, node):
        b = bytearray()
        x = 0
        _len = int(node.attrib['length'])
        for child in node:
            if child.tag == 'Bits':
                for subchild in child:
                    if subchild.tag == 'BitsShortName':
                        bname = subchild.text
                        val = data[bname]['val']
                    elif subchild.tag == 'BitsUnit':
                        if 'scale' in subchild.attrib:
                            scale = subchild.attrib['scale']
                        else:
                            scale = '1.0'
                        val /= float(scale)
                encode = 'int'
                if 'encode' in child.attrib:
                    encode = child.attrib['encode']
                    try:
                        if encode == 'octal':
                            val = int(val, 8)
                        elif encode == 'hex':
                            val = int(val, 16)
                        elif encode == '6bitschar':
                            pass
                        elif encode == 'signed':
                            val = int(val)
                        else:
                            val = int(val)
                    except:
                        print('F:', i, data[bname]['val'], sys.exc_info()[1])
                else:
                    try:
                        val = int(val)
                    except:
                        print('F:', i, data[bname]['val'], sys.exc_info()[1])
                if encode == '6bitschar':
                    for idx, v in enumerate(val[::-1]):
                        shift = idx * 6
                        x |= ((ord(v) & 0x3f) << shift)
                else:
                    if 'from' in child.attrib:
                        fr = int(child.attrib['from'])
                        to = int(child.attrib['to'])
                        dif = int(2 ** (fr - to + 1)) - 1
                        mask = dif << (to - 1)
                        try:
                            x |= (val << (to - 1)) & mask
                        except:
                            print('F:', i, data[bname]['val'], sys.exc_info()[1])
                    elif 'bit' in child.attrib:
                        shift = int(child.attrib['bit']) - 1
                        mask = 1 << shift
                        x |= (data[bname]['val'] << shift) & mask
                    else:
                        pass

        for n in range(_len):
            b.insert(0, x & 0xff)
            x >>= 8
        return b

    def _get_variable(self, i, data, node):
        allbits = set(data.keys())
        b = bytearray()
        for child in node:
            if child.tag == 'Fixed':
                bits = self._get_bits(child)
                if bits.issubset(allbits):
                    if len(b):
                        b[-1] |= 0x01
                    b += self._get_fixed(i, data, child)
            else:
                pass
        return b

    def _get_repetitive(self, i, node):
        b = bytearray()
        b.append(len(self._d[i]))
        for child in node:
            if child.tag == 'Fixed':
                for item in self._d[i]:
                    b += self._get_fixed(i, item, node)
            elif child.tag == 'BDS':
                self._check_xml_cache('bds')
                for item in self._d[i]:
                    b += self._get_bds(i, item, self._xml_cache['bds'].getroot())
            else:
                pass
        return b

    def _get_bds(self, i, data, node):
        self._check_xml_cache('bds')
        b = bytearray()
        for child in node:
            if child.tag == 'DataItem' and data['BDS']['val'] == child.attrib['id']:
                for subchild in child:
                    if subchild.tag == 'DataItemFormat':
                        for recontrasubchild in subchild:
                            if recontrasubchild.tag == 'Fixed':
                                b += self._get_fixed(i, data, recontrasubchild)
                break
        return b

    def _get_bits(self, node):
        bits = set()
        for child in node:
            if child.tag == 'Bits':
                for subchild in child:
                    if subchild.tag == 'BitsShortName':
                        bits.add(subchild.text)
        return bits

    def _get_compound(self, i, data, node):
        b = bytearray()
        children = list(node)
        # el primer nodo de un compound es variable
        if children[0].tag == 'Variable':
            b += self._get_mask(i, data, children[0][0])
            # flatten dict
            d = {}
            for k in data:
                for kk in data[k]:
                    d[kk] = data[k][kk]
            for child in children[1:]:
                # por ahora solo fixed
                if child.tag == 'Fixed':
                    for subchild in child:
                        if subchild.tag == 'Bits':
                            for ccc in subchild:
                                if ccc.tag == 'BitsShortName':
                                    if ccc.text in d:
                                        b += self._get_fixed(i, d, child)
        return b

    def _get_mask(self, i, data, node):
        b = bytearray()
        _len = int(node.attrib['length'])
        x = 0
        for child in node:
            bit = int(child.attrib['bit']) - 1
            for subchild in child:
                if subchild.tag == 'BitsShortName':
                    bname = subchild.text
                    if bname in data:
                        x |= 1 << bit

        for n in range(_len):
            b.insert(0, x & 0xff)
            x >>= 8
        return b

    def _get_explicit(self, i, data, node):
        b = bytearray()
        for child in node:
            # por ahora solo para fixed
            if child.tag == 'Fixed':
                b.append(len(data) + 1)
                for d in data:
                    b += self._get_fixed(i, d, child)
        return b


if __name__ == '__main__':
    import pprint as pp
    # This is binary presentation of asterix packet of CAT048
    #                  len  cat 048
    #                 ---- ---------
    # asterix_packet = bytearray(
    #     [0x30, 0x00, 0x30, 0xfd, 0xf7, 0x02, 0x19, 0xc9, 0x35, 0x6d, 0x4d, 0xa0, 0xc5, 0xaf, 0xf1, 0xe0,
    #      0x02, 0x00, 0x05, 0x28, 0x3c, 0x66, 0x0c, 0x10, 0xc2, 0x36, 0xd4, 0x18, 0x20, 0x01, 0xc0, 0x78,
    #      0x00, 0x31, 0xbc, 0x00, 0x00, 0x40, 0x0d, 0xeb, 0x07, 0xb9, 0x58, 0x2e, 0x41, 0x00, 0x20, 0xf5])

    # asterix_packet = bytearray(b'0\x00D\xff\x01\x01\x04\x99\x08\x82\xe0\x8e@G\x05su\x03\xd9\x01\x1c`\x06\xa8,133794 au 6 blips 2010-03-17 18:36:49.2358\x00')#@\x00\xc4\x99\x02\x04\x0b\x8e')

    asterix_packet = bytearray(b"0\x00H\xff\x01Q\x04\x99\x08|4\xa3@S\'E\x0e\x8c,\x81T`\t\xa6\xc2\x83H\x00\x00+82481 au 9 blips 2010-03-17 17:39:53.4085\x00@\x00\x88V\x01g\xad\xe4")

    parsed = asterix.parse(asterix_packet, verbose=False)
    encoder = AsterixEncoder()
    for data in parsed:
        pp.pprint(data)
        print(list(data.keys()))
        m = encoder.encode(data)
        # pp(data)
        for k in encoder._chunk:
            print(k, encoder.format(encoder._chunk[k]))
        encoder.print(m)
        encoder.print(asterix_packet)
        if m == asterix_packet:
            print('OK!!!!')
        print(data['len'], len(asterix_packet), len(m))
        if len(asterix_packet) == len(m):
            for n in range(len(m)):
                if asterix_packet[n] != m[n]:
                    print('asterix[{}]={:02x} m[{}]={:02x}'.format(n, asterix_packet[n], n, m[n]))
        break

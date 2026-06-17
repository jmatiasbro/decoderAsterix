# -*- coding: utf-8 -*-
from threading import Thread, Event
import logging
import queue
from pprint import pprint  # noqa: F401

# ##############################################################################
from . import constants as K


# ##############################################################################
class Tail2AxMapper(Thread):
    def __init__(self, config, subscriber):
        self._config = config
        self._subscriber = subscriber

        self._input_queue = self._subscriber._output_queue
        self._input_queue_timeout = self._config['mapper']['input_queue_wait_timeout']

        self._output_queue_maxsize = self._config['tail']['output_queue_max_size']
        self._output_queue = queue.Queue(maxsize=self._output_queue_maxsize)
        self._output_queue_wl = int(self._output_queue_maxsize * self._config['tail']['output_queue_warning_level'])
        self._output_queue_timeout = self._config['mapper']['output_queue_wait_timeout']

        self._pkg48 = self._config['mapper']['CAT048']
        self._I020 = {'TYP': {'val': 2}, 'SIM': {'val': 0}, 'RDP': {'val': 0},
                      'SPI': {'val': 0}, 'RAB': {'val': 0}, 'FX': {'val': 0}}
        self._I030 = {'C': {'WE': {'val': self._config['mapper']['WE_C']}, 'FX': {'val': 0}},
                      'S': {'WE': {'val': self._config['mapper']['WE_S']}, 'FX': {'val': 0}}}
        self._I070 = {'V': {'val': 0}, 'G': {'val': 0}, 'L': {'val': 0}, 'Mode3A': {'val': 0}, 'spare': {'val': 0}}
        self._I080 = {'QA4': {'val': 0}, 'QA2': {'val': 0}, 'QA1': {'val': 0},
                      'QB4': {'val': 0}, 'QB2': {'val': 0}, 'QB1': {'val': 0},
                      'QC4': {'val': 0}, 'QC2': {'val': 0}, 'QC1': {'val': 0},
                      'QD4': {'val': 0}, 'QD2': {'val': 0}, 'QD1': {'val': 0},
                      'spare': {'val': 0}
                      }
        self._I090 = {'V': {'val': 0}, 'G': {'val': 0}, 'FL': {'val': 0}}
        self._I220 = {'ACAddr': {'val': 0}}
        self._I240 = {'TId': {'val': 0}}
        self._blip_CCI_seq = ['QD4', 'QB4', 'QD2', 'QB2', 'QD1', 'QB1',
                              'QA4', 'QC4', 'QA2', 'QC2', 'QA1', 'QC1']
        self._ISP = {'C': (('OBA', 'a:{:.2f}'),
                           ('angle', 'b:{:.2f}'),
                           ('phi', 'c:{:.3f}'),
                           # flags. Se agregan al final
                           ('levelI', 'e:{:.2f}'),
                           ('levelD', 'f:{:.2f}'),
                           ('levelDecomp', 'g:{:.2f}'),
                           ('levelOmega', 'h:{:.2f}'),
                           ('RSLS', 'i:{:.2f}'),
                           ('degarblingType', 'j:{}'),
                           ('mode', 'k:{}'),
                           ),
                     'S': (('OBA', 'a:{:.2f}'),
                           ('angle', 'b:{:.2f}'),
                           ('phi', 'c:{:.3f}'),
                           # flags. Se agregan al final
                           ('levelI', 'e:{:.2f}'),
                           ('levelD', 'f:{:.2f}'),
                           ('levelDecomp', 'g:{:.2f}'),
                           ('levelOmega', 'h:{:.2f}'),
                           ('RSLS', 'i:{:.2f}'),
                           ('trackId', 'l:{}'),
                           ('bds', 'm:{}'),
                           # reply['df'] se agrega al final,
                           ),
                     }

        self._setup_logger()
        self._ev = Event()
        self._ev.clear()
        Thread.__init__(self)

    def run(self):
        self._log.info("starting mapper. max_output_queue_size:{}".format(self._output_queue_maxsize))
        while not self._ev.is_set():
            try:
                self._mode, self._flags, self._tail_data = self._input_queue.get(block=True, timeout=self._input_queue_timeout)
                self._log.debug('@{}@ {}'.format(self._mode, self._tail_data))
                self._fill48()
                self._check_output_queue_level()
                try:
                    self._output_queue.put(self._pkg48, block=True, timeout=self._output_queue_timeout)
                except queue.Full:
                    self._log.error("output queue FULL ({} items)".format(self._output_queue_maxsize))
            except queue.Empty:
                pass

    def _check_output_queue_level(self):
        if self._output_queue_maxsize <= 0:
            return
        qs = self._output_queue.qsize()
        if qs >= self._output_queue_wl:
            self._log.warning("output queue over limit ({}/{}) {:.1f}%".format(qs, self._output_queue_maxsize, (qs / self._output_queue_maxsize) * 100))

    def stop(self):
        self._log.info("ending mapper...")
        self._ev.set()

    def _setup_logger(self):
        self._log = logging.getLogger('{}.{}'.format(self._config['logger']['name'],
                                                     self._config['mapper']['log_name']))
        self._log.setLevel(K.LOGGING_LEVEL[self._config['mapper']['log_level']])

    # ----------------------------------------------------------------------------------------------------
    def _fill48(self):
        self._fill48_010()    # I048/010 Data Source Identifier
        self._fill48_140()    # I048/140 Time-of-Day
        self._fill48_020()    # I048/020 Target Report Descriptor
        self._fill48_040()    # I048/040 Measured Position in Slant Polar Coordinates
        self._fill48_070()    # I048/070 Mode-3/A Code in Octal Representation
        self._fill48_090()    # I048/090 Flight Level in Binary Representation
        # self._fill48_130()    # I048/130 Radar Plot Characteristics
        self._fill48_220()    # I048/220 Aircraft Address
        self._fill48_240()    # I048/240 Aircraft Identification
        # self._fill48_250()    # I048/250 Mode S MB Data
        # self._fill48_161()    # I048/161 Track Number
        # self._fill48_042()    # I048/042 Calculated Position in Cartesian Coordinates
        # self._fill48_200()    # I048/200 Calculated Track Velocity in Polar Representation
        # self._fill48_170()    # I048/170 Track Status
        # self._fill48_210()    # I048/210 Track Quality
        self._fill48_030()    # I048/030 Warning/Error Conditions/Target Classification
        self._fill48_080()    # I048/080 Mode-3/A Code Confidence Indicator
        # self._fill48_100()    # I048/100 Mode-C Code and Confidence Indicator
        # self._fill48_110()    # I048/110 Height Measured by 3D Radar
        # self._fill48_120()    # I048/120 Radial Doppler Speed
        # self._fill48_230()    # I048/230 Communications / ACAS Capability and Flight Status
        # self._fill48_260()    # I048/260 ACAS Resolution Advisory Report
        # self._fill48_055()    # I048/055 Mode-1 Code in Octal Representation
        # self._fill48_050()    # I048/050 Mode-2 Code in Octal Representation
        # self._fill48_065()    # I048/065 Mode-1 Code Confidence Indicator
        # self._fill48_060()    # I048/060 Mode-2 Code Confidence Indicator
        self._fill48_SP()    # SP-Data Special Purpose Field
        # self._fill48_RE()     # RE-Data Reserved Expansion Field

    # ----------------------------------------------------------------------------------------------------
    # I048/010 Data Source Identifier
    def _fill48_010(self):
        # esto se resuelve en el archivo de configuracion
        return

    # ----------------------------------------------------------------------------------------------------
    # I048/020 Target Report Descriptor
    def _fill48_020(self):
        if self._mode == 'C':
            self._I020['SPI']['val'] = self._tail_data['flags']['spi']
        else:
            pass
        return

    # ----------------------------------------------------------------------------------------------------
    # I048/030 Warning/Error Conditions/Target Classification
    def _fill48_030(self):
        # falta chequear errores antes de meter el WE
        self._pkg48['I030'] = self._I030[self._mode]

    # ----------------------------------------------------------------------------------------------------
    # I048/040 Measured Position in Slant Polar Coordinates
    def _fill48_040(self):
        self._pkg48['I040']['RHO']['val'] = self._tail_data['distance']
        self._pkg48['I040']['THETA']['val'] = self._tail_data['azimuth']

    # ----------------------------------------------------------------------------------------------------
    # I048/070 Mode-3/A Code in Octal Representation
    def _fill48_070(self):
        if self._mode == 'C':
            if self._tail_data['flags']['validCode']:
                self._send_3A_code(self._tail_data['rxcode']['convModeCode']['code'])
        elif self._mode == 'S':
            if self._tail_data['flags']['validCode'] and self._tail_data['reply']['df'] in (5, 21):
                self._send_3A_code(self._tail_data['reply']['id'])
        else:
            pass

    def _send_3A_code(self, code):
        self._I070['V']['val'] = 0
        self._I070['G']['val'] = 0
        self._I070['L']['val'] = 0
        self._I070['spare']['val'] = 0
        self._I070['Mode3A']['val'] = '{0:o}'.format(code)
        self._pkg48['I070'] = self._I070

    # ----------------------------------------------------------------------------------------------------
    # I048/080 Mode-3/A Code Confidence Indicator
    # blip: x  F1 C1 A1 C2 A2 C4 A4 B1 D1 B2 D2 B4 D4 F2 SPI
    # ax48: 0  0  0  0  A4 A2 A1 B4 B2 B1 C4 C2 C1 D4 D2 D1
    def _fill48_080(self):
        if self._mode == 'C':
            if self._tail_data['flags']['validCode']:
                r = ~(self._tail_data['rxcode']['convModeCode']['reliability'] & 0x7fff >> 2) & 0x0fff
                for qcode in self._blip_CCI_seq:
                    self._I080[qcode]['val'] = r & 1
                    r >>= 1
                self._pkg48['I080'] = self._I080
        else:
            pass

    # ----------------------------------------------------------------------------------------------------
    # I048/090 Flight Level in Binary Representation
    def _fill48_090(self):
        if self._mode == 'C':
            if self._tail_data['flags']['validCode']:
                code_c = self._tail_data['rxcode']['convModeCode']['code'] & 0x7fff
                ok, fl = self._get_altitude(code_c)
                if ok:
                    self._send_fl(fl)

        elif self._mode == 'S':
            if self._tail_data['flags']['validCode'] and self._tail_data['reply']['df'] in (4, 20):
                code_c = 0
                ac = self._tail_data['reply']['ac']
                m_bit = bool(ac & 0x40)
                if not m_bit:
                    # M bit == 0
                    q_bit = bool(ac & 0x10)
                    if not q_bit:
                        # Q bit == 0
                        # See [R1], 3.1.2.6.5.4 AC: Altitude code, item c)

                        # Map member "ac" from (see [R1], 3.1.2.6.5 Surveillance altitude
                        # reply, downlink format 4)
                        # |  x  x  x 20 21 22 23 24 25 26 27 28 29 30 31 32 |
                        # | 16 15 14 13 12 11 10  9  8  7  6  5  4  3  2  1 |
                        # |  0  0  0 C1 A1 C2 A2 C4 A4  M B1  Q B2 D2 B4 D4 |
                        # to ASTERIX mode C code pulse order (see [R2], 5.2.13 Data Item
                        # I048/100, Mode-C Code and Confidence Indicator), i.e.
                        # | 16 15 14 13 12 11 10  9  8  7  6  5  4  3  2  1 |
                        # |  0  0  0  0 C1 A1 C2 A2 C4 A4 B1  0 B2 D2 B4 D4 |
                        # remember that for code C the pulse D1 is always 0!
                        code_c = ((ac & 0x1F80) >> 1) | (ac & 0x003F)
                        # 0x1F80 = 1 1111 1000 0000
                        # 0x003F = 0 0000 0011 1111

                        # Map "code_c" from
                        # | 16 15 14 13 12 11 10  9  8  7  6  5  4  3  2  1 |
                        # |  0  0  0  0 C1 A1 C2 A2 C4 A4 B1  0 B2 D2 B4 D4 |
                        # to
                        # | 16 15 14 13 12 11 10  9  8  7  6  5  4  3  2  1 |
                        # |  0  0  0  0 A4 A2 A1 B4 B2 B1 C4 C2 C1 D4 D2 D1 |
                        aux = ((code_c & 0x040) << 5) \
                            | ((code_c & 0x100) << 2) \
                            | ((code_c & 0x400) >> 1) \
                            | ((code_c & 0x002) << 7) \
                            | ((code_c & 0x008) << 4) \
                            | ((code_c & 0x020) << 1) \
                            | ((code_c & 0x080) >> 2) \
                            | ((code_c & 0x200) >> 5) \
                            | ((code_c & 0x800) >> 8) \
                            | ((code_c & 0x001) << 2) \
                            | ((code_c & 0x004) >> 1) \
                            | ((code_c & 0x010) >> 4)
                        ok, fl = self._get_altitude(aux)
                        if ok:
                            self._send_fl(fl)

                    else:
                        # Q bit == 1
                        # See [R1], 3.1.2.6.5.4 AC: Altitude code, item d)

                        # N is the 11 bit integer resulting from the removal of bits Q and M
                        N = ((ac & 0x1F80) >> 2) \
                            | ((ac & 0x0020) >> 1) \
                            | (ac & 0x000F)
                        # 0x1F80 = 1 1111 1000 0000
                        # 0x0020 = 0 0000 0010 0000
                        # 0x003F = 0 0000 0000 1111

                        # Compute altitude
                        fl = int((25 * N - 1000) / 100)
                        self._send_fl(fl)
                else:
                    # M bit == 1
                    # ERROR: reserved for a future encoding in metric units
                    pass
        else:
            pass

    def _get_altitude(self, code_c):
        ok = False
        fl = 0
        if code_c >= 0 and code_c < K.MAX_MODE_C_CODE:
            fl = K.FL_TABLE[code_c >> 1]
            if fl != K.ERROR:
                ok = True
        return (ok, fl)

    def _send_fl(self, fl):
        self._I090['V']['val'] = 0
        self._I090['G']['val'] = 0
        self._I090['FL']['val'] = fl * 4
        self._pkg48['I090'] = self._I090

    # ----------------------------------------------------------------------------------------------------
    # I048/140 Time-of-Day
    def _fill48_140(self):
        self._pkg48['I140']['ToD']['val'] = float(self._tail_data['timeSec'] + self._tail_data['timeNsec'] * 1e-9)

    # ----------------------------------------------------------------------------------------------------
    # I048/220 Aircraft Address
    def _fill48_220(self):
        if self._mode == 'S':
            self._I220['ACAddr']['val'] = '{:06X}'.format(self._tail_data['reply']['aa'])
            self._pkg48['I220'] = self._I220
        else:
            pass

    # ----------------------------------------------------------------------------------------------------
    # I048/240 Aircraft Identification
    def _fill48_240(self):
        if self._mode == 'S':
            if self._tail_data['flags']['validCode'] and self._tail_data['reply']['df'] in (20, 21):
                # maybe should test self._tail_data['bds'] == 0x20
                if self._tail_data['reply']['mb'][0] == 0x20:
                    mb = self._tail_data['reply']['mb']
                    tid = [0, 0, 0, 0, 0, 0, 0, 0]
                    tid[0] = (mb[1] >> 2) & 0x3f
                    tid[1] = ((mb[1] << 4) | (mb[2] >> 4)) & 0x3f
                    tid[2] = ((mb[2] << 2) | (mb[3] >> 6)) & 0x3f
                    tid[3] = mb[3] & 0x3f
                    tid[4] = (mb[4] >> 2) & 0x3f
                    tid[5] = ((mb[4] << 4) | (mb[5] >> 4)) & 0x3f
                    tid[6] = ((mb[5] << 2) | (mb[6] >> 6)) & 0x3f
                    tid[7] = mb[6] & 0x3f
                    for n in range(8):
                        tid[n] = chr(tid[n]) if tid[n] & 0x20 else chr(tid[n] | 0x40)
                    self._I240['TId']['val'] = ''.join(tid)
                    self._pkg48['I240'] = self._I240
        else:
            pass

    # ----------------------------------------------------------------------------------------------------
    # SP-Data Special Purpose Field
    def _fill48_SP(self):
        s = [fmt.format(self._tail_data[key]) for key, fmt in self._ISP[self._mode]]
        s.append('d:0x')
        for f in tuple(self._flags):
            s.append('{:02X}'.format(f))
        if self._mode == 'S':
            s.append('n:{}'.format(self._tail_data['reply']['df']))
        self._pkg48['ISP'] = self._build_sp('|'.join(s))

    def _build_sp(self, data):
        sp = [{'SP': {'val': ord(v)}} for v in str(data)]
        sp.append({'SP': {'val': 0}})
        return sp

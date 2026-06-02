from ctypes import *
import collections
import json
import os
import numpy


class RsmasStructure(Structure):
    @classmethod
    def from_dict(cls, dict_):
        '''
        Create an instance of a RsmasStructure from a dict with field names and
        values
        '''

        # this will not work correctly if there are fields with the same name
        # inside the structure
        def get_context(field_name, structure):
            ctx = None

            # create dict from list of tuples (cannot unpack structure._fields_
            # because its tuples may have 2 or 3 (C bitfields) items, but always
            # the first item is the field name and the second one its value
            fields = {field[0]:field[1] for field in structure._fields_}

            # check if "field_name" is in this context; search inside structures
            # if not
            if field_name in fields.keys():
                ctx = structure
            else:
                for field in fields.keys():
                    if ctx == None and hasattr(getattr(structure, field), "_fields_"):
                        ctx = get_context(field_name, getattr(structure, field))

            return ctx

        # create an empty instance
        struct = cls()

        # fill instance
        for key, value in dict_.items():
            ctx = get_context(key, struct)
            if ctx:
                # Probably anothet struct
                # Use for interrogation reports in PLOT_S_T
                if isinstance(value, dict):
                    sub_struct = getattr(ctx, key)
                    sub_struct_value = sub_struct.from_dict(value)
                    setattr(ctx, key, sub_struct_value)
                elif isinstance(value, list):
                    for i, each_value in enumerate(value):
                        arr = getattr(ctx, key)
                        # Probably anothet struct
                        # Use for messageCommB in PLOT_S_T
                        if isinstance(each_value, dict):
                            sub_struct_value = arr[i].from_dict(each_value)
                            arr[i] = sub_struct_value
                        else:
                            arr[i] = each_value
                        setattr(ctx, key, arr)
                elif isinstance(value, str):
                    # Convert from ascii to ia5
                    ascii_bin = [bin(ord(x))[2:].zfill(8) for x in value]
                    ia5_bin = ''.join(x[2:] for x in ascii_bin)
                    ia5_list = list(
                        int(ia5_bin[i:i + 8], 2)
                        for i in range(0, len(ia5_bin), 8))
                    # Set new value
                    for i, each_value in enumerate(ia5_list):
                        arr = getattr(ctx, key)
                        arr[i] = each_value
                        setattr(ctx, key, arr)
                else: # primitive types
                    setattr(ctx, key, value)
            else:
                # Special case for TIMESPEC
                if "TimeSec" in key or "timeSec" in key:
                    # Get Sec item value
                    time_spec = TIMESPEC()
                    setattr(time_spec, "tv_sec", value)
                    # Get Nsec item value
                    nsec_key = key.replace("Sec", "Nsec")
                    nsec_value = dict_[nsec_key]
                    setattr(time_spec, "tv_nsec", nsec_value)
                    # Set new timespec
                    timespec_key = key.replace("Sec", "")
                    setattr(struct, timespec_key, time_spec)
                elif key == "time":
                    time_spec = TIMESPEC()
                    setattr(time_spec, "tv_sec", value)
                    setattr(time_spec, "tv_nsec", 0)
                    setattr(struct, key, time_spec)
                elif "Nsec" in key:
                    # Nothing to do because it was already done in the "if" of TimeSec
                    pass

        return struct

    @classmethod
    def from_json(cls, str_):
        # copy-pasted from https://stackoverflow.com/a/6027615
        def flatten(d, parent_key='', sep='_'):
            items = []
            for k, v in d.items():
                new_key = parent_key + sep + k if parent_key else k
                if isinstance(v, collections.MutableMapping):
                    items.extend(flatten(v, new_key, sep=sep).items())
                else:
                    items.append((new_key, v))
            return dict(items)

        # create nested dict
        dict_ = json.loads(str_)

        # flatten dict
        dict_ = flatten(dict_, sep='.')

        # delete parent key substring from keys
        for k in dict_.keys():
            if '.' in k:
                new_k = k[k.rfind('.') + 1:]
                dict_[new_k] = dict_.pop(k)

        return cls.from_dict(dict_)

    def to_dict(self):
        '''
        Return a field_name:field_value dictionary of a ctypes.Structure.
        '''
        dict_ = dict()
        for field_values in self._fields_:
            # unpack field tuple
            name = field_values[0]
            type_ = field_values[1]

            # get field value
            value = getattr(self, name)

            # store field in dictionary
            try:
                # timespec type
                dict_[name + 'Sec'] = getattr(value, 'tv_sec')
                dict_[name + 'Nsec'] = getattr(value, 'tv_nsec')
            except:
                # array type
                if 'Array' in str(type_):
                    dict_[name] = list()
                    size = len(value)
                    for i in range(size):
                        # If another struct
                        if hasattr(value[i], "_fields_"):
                            dict_[name].append(value[i].to_dict())
                        else:
                            dict_[name].append(value[i])
                # another struct
                elif hasattr(value, "_fields_"):
                    dict_[name] = value.to_dict()
                # other data types (c_bool, c_uint8, etc)
                else:
                    dict_[name] = value

        return dict_

    def to_json(self, pretty=True):
        '''
        Esta función convierte una struct C a JSON format
        '''

        if pretty:
            str_ = json.dumps(self.to_dict(), indent=2)
        else:
            str_ = json.dumps(self.to_dict())

        return str_


class TIMESPEC(Structure):
    _fields_ = [('tv_sec', c_long), ('tv_nsec', c_long)]


class FLAGS_T(RsmasStructure):
    _pack_ = 1
    _fields_ = [('spi', c_uint16, 1), ('slr', c_uint16, 1), ('tst', c_uint16, 1),
                ('rab', c_uint16, 1), ('errOba', c_uint16, 1),
                ('errDist', c_uint16, 1), ('errAng', c_uint16, 1),
                ('stc', c_uint16, 1), ('validCode', c_uint16, 1),
                ('validOba', c_uint16, 1), ('errGar', c_uint16, 1),
                ('emg', c_uint16, 1), ('spare', c_uint16, 4)]


class CONV_MODE_CODE_T(RsmasStructure):
    _fields_ = [('code', c_int), ('pulse', c_int), ('reliability', c_int)]
    _defaults_ = {'code': 0, 'pulse': 0, 'reliability': 0}


class RXCODE_UNION_T(Union):
    _fields_ = [('convModeCode', CONV_MODE_CODE_T)]

    # FIXME: this method makes this class seems like a "RsmasStructure", at
    # least to the "to_dict" eyes, so the call to method "to_dict" on an object
    # of the class "BLIP_T" works correctly...the fix should be the deletion of
    # the corresponding useless union from the structure "blip_t"
    def to_dict(self):
        fixme = RsmasStructure()
        setattr(fixme, '_fields_', self._fields_)
        setattr(fixme, 'convModeCode', self.convModeCode)

        return fixme.to_dict()


# rtp_libblip/include/libblip/blip.h
class BLIP_T(RsmasStructure):
    _fields_ = [('flags', FLAGS_T), ('angle', c_float), ('azimuth', c_float),
                ('level', c_float), ('levelI', c_float), ('levelD', c_float), 
                ('levelOmega', c_float), ('levelDecomp', c_float), ('OBA', c_float), 
                ('phi', c_float), ('distance', c_float), ('RSLS', c_float), 
                ('time', TIMESPEC), ('timePresent', c_bool), ('rxcode', RXCODE_UNION_T),
                ('mode', c_uint), ('degarblingType', c_uint)]


class MODE_S_REPLY(RsmasStructure):
    _fields_ = [('df', c_uint8), ('ca', c_uint8), ('aa', c_uint32),
                ('fs', c_uint8), ('dr', c_uint8), ('um', c_uint8),
                ('ac', c_uint16), ('id', c_uint16), ('mb', 7 * c_uint8)]


class BLIP_S_T(RsmasStructure):
    _fields_ = [('angle', c_float), ('azimuth', c_float), ('level', c_float),
                ('levelI', c_float), ('levelD', c_float),
                ('levelOmega', c_float), ('levelDecomp', c_float), ('OBA', c_float),
                ('phi', c_float), ('distance', c_float), ('RSLS', c_float), ('time', TIMESPEC),
                ('flags', FLAGS_T), ('retriggered', c_bool), ('si_capable', c_bool),
                ('trackId', c_uint32), ('bds', c_uint),
                ('aircraft_address', c_uint32), ('reply', MODE_S_REPLY)]

    @staticmethod
    def from_json(str_):
        # TODO: it would be so much better if modelística send the altitude
        # engineering value
        def decode_gillham(ac):
            import numpy
            altitude_feet, _, squawk = numpy.loadtxt(
                os.path.dirname(os.path.abspath(__file__)) +
                '/gillham_code.csv',
                delimiter=',',
                dtype='int,float,U4',
                skiprows=1,
                unpack=True)
            ac_oct = oct(ac)

            value = altitude_feet[numpy.where(squawk == ac_oct[2:])]

            return value.item()

        blip = BLIP_S_T()

        data = json.loads(str_)
        blip.angle = data['angle']
        blip.azimuth = data['azimuth']
        blip.level = data['level']

        try:
            blip.levelOmega = data['levelOmega']
        except:
            blip.levelOmega = 0

        try:
            blip.levelDecomp = data['levelDecomp']
        except:
            blip.levelDecomp = 0

        blip.OBA = data['OBA']
        blip.distance = data['distance']
        blip.aircraft_address = int(data['rxcode']['modeSCode']['AA'])

        try:
            blip.RSLS = data['RSLS']
        except:
            blip.RSLS = 0

        # NOTE: this is because AySC didn't add the key/value pair "trackId" to
        # blips conveying all-call replies
        try:
            blip.trackId = data['trackID']
        except:
            blip.trackId = 0

        #FLAGS
        blip.flags.spi = data['flags']['spi']
        blip.flags.slr = data['flags']['slr']
        blip.flags.errOba = data['flags']['errOba']
        blip.flags.errDist = data['flags']['errDist']
        blip.flags.errAng = data['flags']['errAng']
        blip.flags.validCode = data['flags']['validCode']
        blip.flags.errGar = data['flags']['errGar']
        blip.flags.emg = data['flags']['emg']

        # MODE_S_REPLY
        blip.reply.df = data['rxcode']['modeSCode']['DF']

        if blip.reply.df == 11:
            blip.reply.ca = data['rxcode']['modeSCode']['CA']
            blip.reply.aa = int(data['rxcode']['modeSCode']['AA'])
        elif blip.reply.df in set([4, 5, 20, 21]):
            blip.reply.fs = data['rxcode']['modeSCode']['FS']
            blip.reply.dr = data['rxcode']['modeSCode']['DR']
            blip.reply.um = data['rxcode']['modeSCode']['UM']

            if blip.reply.df == 4 or blip.reply.df == 20:
                # read decimal representation
                code_c = data['rxcode']['modeSCode']['AC']

                # compute altitude
                altitude = decode_gillham(code_c) # [ft]

                # compute field AC
                ac = ""
                if altitude <= 50187.5: # [50187.5] = ft
                    # compute altitude counts (1 count = 25 ft)
                    N = (altitude + 1000) // 25

                    # get bits
                    b20, b21, b22, b23, b24, b25, b27, b29, b30, b31, b32 = numpy.binary_repr(N, width=11)

                    # compute field AC
                    m = "0"
                    q = "1"
                    ac = b20 + b21 + b22 + b23 + b24 + b25 + m + b27 + q + b29 + b30 + b31 + b32
                else:
                    # get bits
                    a4, a2, a1, b4, b2, b1, c4, c2, c1, d4, d2, _ = numpy.binary_repr(code_c, width=12)

                    # compute field AC
                    m = "0"
                    q = "0"
                    ac = c1 + a1 + c2 + a2 + c4 + a4 + m + b1 + q + b2 + d2 + b4 + d4

                # set AC in mode S reply
                blip.reply.ac = int(ac, 2)

            if blip.reply.df == 5 or blip.reply.df == 21:
                # read decimal representation
                code_a = data['rxcode']['modeSCode']['ID'] # A4 A2 A1 B4 B2 B1 C4 C2 C1 D4 D2 D1

                # get bits
                a4, a2, a1, b4, b2, b1, c4, c2, c1, d4, d2, d1 = numpy.binary_repr(code_a, width=12)

                # compute field ID
                id_ = c1 + a1 + c2 + a2 + c4 + a4 + '0' + b1 + d1 + b2 + d2 + b4 + d4

                # set ID in mode S reply
                blip.reply.id = int(id_, 2)

            if blip.reply.df == 20 or blip.reply.df == 21:
                try:
                    blip.bds = int(str(data['rxcode']['modeSCode']['MB']['BDS']), 16)
                    aux = [
                        int(b) for b in data['rxcode']['modeSCode']['MB']['code'].to_bytes(
                            TRANSPONDER_REGISTER_T.SIZE, byteorder='big')
                    ]
                    for i, byte in enumerate(aux):
                        blip.reply.mb[i] = byte
                except:
                    blip.bds = 0
                    for i in range(TRANSPONDER_REGISTER_T.SIZE):
                        blip.reply.mb[i] = 0
        else:
            raise ValueError('Unrecognized mode S message type {}'.format(
                blip.reply.df))

        return blip


# libplot/include/libplot/plot.h
class PLOT_T(RsmasStructure):
    _fields_ = [('psr', c_bool), ('ssr', c_bool), ('sim', c_bool),
                ('spi', c_bool), ('rab', c_bool), ('tst', c_bool),
                ('me', c_bool), ('mi', c_bool), ('distance', c_float),
                ('azimuth', c_float), ('flightLevel', c_int16),
                ('code1', c_uint16), ('code2', c_uint16), ('codeA', c_uint16),
                ('codeC', c_uint16), ('code1Reliability', c_uint16),
                ('code2Reliability', c_uint16), ('codeAReliability', c_uint16),
                ('codeCReliability', c_uint16), ('code1Present', c_bool),
                ('code2Present', c_bool), ('codeAPresent', c_bool),
                ('codeCPresent', c_bool), ('code1Garbled', c_bool),
                ('code2Garbled', c_bool), ('codeAGarbled', c_bool),
                ('codeCGarbled', c_bool), ('code1Smoothed', c_bool),
                ('code2Smoothed', c_bool), ('codeASmoothed', c_bool),
                ('code1Validated', c_bool), ('code2Validated', c_bool),
                ('codeAValidated', c_bool), ('codeCValidated', c_bool),
                ('run', c_uint8), ('num', c_uint8), ('amp', c_int8),
                ('runPresent', c_bool), ('numPresent', c_bool),
                ('ampPresent', c_bool), ('errGar', c_bool), ('errRlx', c_bool),
                ('errSlr', c_bool), ('errOba', c_bool), ('errDist', c_bool),
                ('errAng', c_bool), ('errCodeA', c_bool), ('errCodeC', c_bool),
                ('errPhantom', c_bool), ('early', c_bool),
                ('report', c_bool), ('timePresent', c_bool),
                ('time', TIMESPEC), ('pTime', TIMESPEC),
                ('trackTime', TIMESPEC)]


class TRANSPONDER_REGISTER_T(RsmasStructure):
    SIZE = 7  #Number of bytes in COMM-B
    _fields_ = [('bytes', c_uint8 * SIZE)]


class BDS_REGISTER_T(RsmasStructure):
    _fields_ = [('bds', c_uint), ('register_', TRANSPONDER_REGISTER_T)]


class REQUEST_LIST_T(RsmasStructure):
    MAXIMUM_REQUEST_LIST_LENGTH = 12

    _fields_ = [('air', c_bool), ('length', c_uint8),
                ('requests', c_int * MAXIMUM_REQUEST_LIST_LENGTH)]


# Only for creating structures corresponding to mode S plots
class INTERROGATION_REPORT_T(RsmasStructure):
    _fields_ = [('trackId', c_uint32), ('time', TIMESPEC),
                ('pendingRequests', REQUEST_LIST_T)]

    @staticmethod
    def from_json(str_):
        data = json.loads(str_)

        struct = INTERROGATION_REPORT_T()
        struct.trackId = data['trackID']
        struct.pendingRequests.air = data['AIR']
        for i, request in enumerate(data['transactionPending']):
            struct.pendingRequests.requests[i] = request
            struct.pendingRequests.length += 1

        return struct


# libplot/include/libplot/plot_s.h
class PLOT_S_T(RsmasStructure):
    MAXIMUM_MODE_S_REPLIES = 32  #Maximum replies per mode S plot report
    _fields_ = [('sim', c_bool), ('spi', c_bool), ('rab', c_bool),
                ('tst', c_bool), ('me', c_bool), ('mi', c_bool),
                ('distance', c_float), ('azimuth', c_float),
                ('flightLevel', c_int16), ('aircraftAddress', c_uint32),
                ('codeA', c_uint16),
                ('run', c_uint8), ('num', c_uint8), ('amp', c_int8),
                ('runPresent', c_bool), 
                ('ampPresent', c_bool), ('errRlx', c_bool), ('errSlr', c_bool),
                ('errOba', c_bool), ('errDist', c_bool), ('errAng', c_bool),
                ('errAa', c_bool), ('errAlt', c_bool),
                ('downLink', c_uint8 * MAXIMUM_MODE_S_REPLIES),
                ('capability', c_uint8), ('flightStatus', c_uint8),
                ('downlinkRequest', c_uint8), ('utilityMessage', c_uint8),
                ('messageCommB', BDS_REGISTER_T * MAXIMUM_MODE_S_REPLIES),
                ('siCapable', c_bool),
                ('early', c_bool),('report', c_bool),
                ('time', TIMESPEC),
                ('pTime', TIMESPEC), ('trackTime', TIMESPEC),
                ('interrogationReport', INTERROGATION_REPORT_T)]

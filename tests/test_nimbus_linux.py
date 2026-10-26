import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import nimbus_linux as n


def report(**kw):
    """Monta um relatório de 17 bytes: report(A=255, L2=128, stickL_y=100)."""
    r = bytearray(n.REPORT_LEN)
    for name, v in kw.items():
        r[n.NAMES.index(name)] = v & 0xFF
    return bytes(r)


def ev(r, **kw):
    prof = kw.pop("profile", "standard")
    return {(t, c): v for t, c, v in n.translate(r, prof, **kw)}


class Translate(unittest.TestCase):
    def test_repouso(self):
        e = ev(report())
        self.assertTrue(all(v == 0 for v in e.values()))

    def test_botoes_standard(self):
        e = ev(report(A=255, B=1, Y=255, L1=255))
        self.assertEqual((e[n.EV_KEY, n.BTN_SOUTH], e[n.EV_KEY, n.BTN_EAST]), (1, 1))
        self.assertEqual((e[n.EV_KEY, n.BTN_NORTH], e[n.EV_KEY, n.BTN_WEST]), (0, 1))
        self.assertEqual((e[n.EV_KEY, n.BTN_TL], e[n.EV_KEY, n.BTN_TR]), (1, 0))

    def test_botoes_game_na_faixa_joystick(self):
        e = ev(report(A=255, R1=255), profile="game")
        self.assertEqual((e[n.EV_KEY, 0x120], e[n.EV_KEY, 0x125]), (1, 1))
        self.assertNotIn((n.EV_KEY, n.BTN_SOUTH), e)  # senão o SDL vê um gamepad

    def test_home(self):
        r = report(home=1)
        self.assertEqual(ev(r)[n.EV_KEY, n.BTN_START], 1)
        self.assertEqual(ev(r, home="mode")[n.EV_KEY, n.BTN_MODE], 1)
        self.assertEqual(ev(r, profile="game")[n.EV_KEY, n.GAME_HOME], 1)

    def test_combinacoes_do_home(self):
        e = ev(report(home=1, L1=255))
        self.assertEqual((e[n.EV_KEY, n.BTN_THUMBL], e[n.EV_KEY, n.BTN_START], e[n.EV_KEY, n.BTN_TL]), (1, 0, 0))
        e = ev(report(home=1, R1=255))
        self.assertEqual((e[n.EV_KEY, n.BTN_THUMBR], e[n.EV_KEY, n.BTN_START], e[n.EV_KEY, n.BTN_TR]), (1, 0, 0))
        e = ev(report(home=1, L1=255, R1=255))
        self.assertEqual((e[n.EV_KEY, n.BTN_SELECT], e[n.EV_KEY, n.BTN_THUMBL], e[n.EV_KEY, n.BTN_TL]), (1, 0, 0))
        e = ev(report(L1=255))  # sem Home, L1 segue sendo L1
        self.assertEqual((e[n.EV_KEY, n.BTN_TL], e[n.EV_KEY, n.BTN_THUMBL]), (1, 0))
        e = ev(report(home=1, L1=255), profile="game")
        self.assertEqual((e[n.EV_KEY, n.GAME_THUMBL], e[n.EV_KEY, 0x124]), (1, 0))

    def test_home_modo_mode_nao_tem_combinacao(self):
        e = ev(report(home=1, L1=255), home="mode")
        self.assertEqual((e[n.EV_KEY, n.BTN_MODE], e[n.EV_KEY, n.BTN_TL], e[n.EV_KEY, n.BTN_THUMBL]), (1, 1, 0))

    def test_gatilhos_analogicos_passam_direto(self):
        e = ev(report(L2=77, R2=200))
        self.assertEqual((e[n.EV_ABS, n.ABS_Z], e[n.EV_ABS, n.ABS_RZ]), (77, 200))

    def test_dpad(self):
        e = ev(report(dpad_up=255, dpad_right=255))
        self.assertEqual((e[n.EV_ABS, n.ABS_HAT0X], e[n.EV_ABS, n.ABS_HAT0Y]), (1, -1))
        e = ev(report(dpad_down=255, dpad_left=255))
        self.assertEqual((e[n.EV_ABS, n.ABS_HAT0X], e[n.EV_ABS, n.ABS_HAT0Y]), (-1, 1))
        e = ev(report(dpad_up=n.DPAD_ON - 1))  # abaixo do limiar não conta
        self.assertEqual(e[n.EV_ABS, n.ABS_HAT0Y], 0)

    def test_stick_cima_vira_negativo(self):
        e = ev(report(stickL_y=127, stickR_y=-127, stickL_x=127, stickR_x=-127))
        self.assertEqual(e[n.EV_ABS, n.ABS_Y], -32767)
        self.assertEqual(e[n.EV_ABS, n.ABS_RY], 32767)
        self.assertEqual(e[n.EV_ABS, n.ABS_X], 32767)
        self.assertEqual(e[n.EV_ABS, n.ABS_RX], -32767)

    def test_flip_y(self):
        self.assertEqual(ev(report(stickL_y=127), flip_y=True)[n.EV_ABS, n.ABS_Y], 32767)

    def test_stick_extremo_nao_estoura(self):
        self.assertEqual(n.stick(-128), -32768)
        self.assertEqual(n.stick(0), 0)


class Config(unittest.TestCase):
    def test_gatilhos_do_game_sao_centralizados(self):
        z = {c: lo for c, lo, *_ in n.abs_setup("game")}
        self.assertEqual((z[n.ABS_Z], z[n.ABS_RZ]), (-255, -255))
        z = {c: lo for c, lo, *_ in n.abs_setup("standard")}
        self.assertEqual((z[n.ABS_Z], z[n.ABS_RZ]), (0, 0))

    def test_pedal_usa_curso_inteiro_e_botoes_joystick(self):
        z = {c: lo for c, lo, *_ in n.abs_setup("pedal")}
        self.assertEqual((z[n.ABS_Z], z[n.ABS_RZ]), (0, 0))
        e = ev(report(A=255), profile="pedal")
        self.assertEqual(e[n.EV_KEY, 0x120], 1)
        self.assertNotIn((n.EV_KEY, n.BTN_SOUTH), e)

    def test_read_profile(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "profile")
            self.assertEqual(n.read_profile(p), "standard")  # ausente
            for text, want in (("game\n", "game"), ("standard", "standard"), ("lixo", "standard")):
                with open(p, "w") as f:
                    f.write(text)
                self.assertEqual(n.read_profile(p), want)


if __name__ == "__main__":
    unittest.main()

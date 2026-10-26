# nimbus-for-linux

Suporte nativo no Linux ao controle **SteelSeries Nimbus** (Bluetooth, MFi).

[English](README.md)

O Nimbus foi feito para dispositivos Apple. No Linux, o driver padrão `hid-generic` o trata mal:

- o D-pad fica preso em "cima" (`ABS_HAT0Y = -1` o tempo todo);
- os gatilhos analógicos (L2/R2) viram botões liga/desliga;
- jogos do Steam, SDL e Wine recebem um controle meio quebrado.

O `nimbus-for-linux` corrige isso em espaço de usuário: lê os relatórios HID brutos do controle e expõe um gamepad virtual correto via `uinput`. É Python puro (só biblioteca padrão), sem módulo de kernel e sem root em tempo de execução.

## Instalação

```sh
git clone https://github.com/dbcfilho/nimbus-for-linux.git
cd nimbus-for-linux
./install.sh
```

Requisitos: Linux com `uinput`, systemd, Python ≥ 3.8 e `sudo` (uma vez, para a regra udev). Pareie o controle pelo Bluetooth normalmente e acompanhe:

```sh
journalctl --user -u nimbus-linux -f
```

Para remover tudo: `./install.sh --uninstall`.

## Mapeamento dos botões

| Nimbus | Gamepad virtual |
|---|---|
| A, B, X, Y, L1, R1 | A, B, X, Y, LB, RB |
| L2, R2 (analógicos) | LT, RT (analógicos) |
| Home | Start |
| L1 + Home | L3 (clique do analógico esquerdo) |
| R1 + Home | R3 (clique do analógico direito) |
| L1 + R1 + Home | Back / Select |

As combinações com o Home seguem o mapeamento do [MFIGamepadFeeder](https://github.com/Axadiw/MFIGamepadFeeder), a ferramenta do Windows que faz o mesmo trabalho lá.

## Perfis

| Perfil | Se apresenta como | Para quê |
|---|---|---|
| `standard` (padrão) | Xbox 360 (`045e:028e`), layout do xpad | Steam, SDL, Proton, emuladores |
| `game` | joystick cru (`0111:1420`), botões na faixa `BTN_JOYSTICK`, gatilhos centralizados | jogos DirectInput antigos no Wine |

```sh
nimbus-profile          # mostra o perfil atual
nimbus-profile game     # troca; o daemon recarrega por SIGHUP, sem reconectar o controle
```

No Lutris, use `nimbus-profile game` como comando de pré-lançamento e `nimbus-profile standard` como comando pós-saída.

## Wine e jogos antigos

O DirectInput configura cada eixo com faixa simétrica, então um gatilho em repouso no mínimo parece totalmente apertado, e o Wine funde os dois gatilhos num eixo Z quando o SDL vê um gamepad. O perfil `game` evita as duas coisas. A explicação completa, com o estudo de caso do *Need for Speed: Most Wanted* (2005), está em [docs/wine-games.md](docs/wine-games.md).

**Dica para o NFSMW com o Widescreen Fix:** se o remapeamento de controles travar e os eixos aparecerem como "LT / RT", ponha `ImproveGamepadSupport = 0` em `scripts/NFSMostWanted.WidescreenFix.ini`. Nos nossos testes isso destravou o remapeamento. Faça backup do `.ini` antes.

## Opções, protocolo e limitações

- Opções: `nimbus-linux --help` (`--monitor SEGUNDOS` mostra os relatórios brutos).
- Protocolo de 17 bytes: [docs/protocol.md](docs/protocol.md).
- LED de jogador: o LED 1 acende ao conectar (`--led 0` desliga, `--led 2/4/8` escolhe outro).
- Testado em um controle e uma máquina (Debian 13, kernel 7.1, Wine-GE 8). Relatos de outras distribuições são bem-vindos.

## Desenvolvimento

```sh
python3 -m unittest discover -s tests -v
```

## Licença

MIT, veja [LICENSE](LICENSE).

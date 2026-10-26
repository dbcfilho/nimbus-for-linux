# nimbus-linux

Driver em espaço de usuário para o **SteelSeries Nimbus** (Bluetooth, `0111:1420`) no Linux.
Python puro (stdlib), sem dependências, sem módulo de kernel, sem root em tempo de execução.

## Por que existe

O `hid-generic` do kernel não entende o relatório do Nimbus: o D-pad fica preso em "cima" e os
gatilhos L2/R2 (analógicos de verdade) viram botões liga/desliga. O `hid-steelseries` só cobre o
Nimbus USB (`1038`). Este daemon lê o relatório bruto pelo hidraw e cria um gamepad correto via uinput.

## Instalação

```sh
./install.sh              # instala em ~/.local/bin, liga o serviço de usuário; sudo só para a regra udev
./install.sh --uninstall
```

Requisitos: Linux com `uinput`, systemd, `python3` ≥ 3.8, `sudo` (uma vez, para a regra udev).
Confira o resultado com `journalctl --user -u nimbus-linux -f` e ligue o controle.

## Perfis

| Perfil | Identidade | Para quê |
|---|---|---|
| `standard` (padrão) | Xbox 360 (`045e:028e`), layout do xpad, L2/R2 em `ABS_Z/RZ` 0..255 | SDL, Steam, Proton, emuladores |
| `game` | joystick cru `0111:1420`, botões em `BTN_JOYSTICK`, gatilhos centralizados (−255..255) | jogos DirectInput antigos via Wine (ex.: NFS Most Wanted) |

```sh
nimbus-profile          # mostra o perfil atual
nimbus-profile game     # troca; o daemon recarrega por SIGHUP, sem reconectar o controle
```

No Lutris, use `nimbus-profile game` em *prelaunch* e `nimbus-profile standard` em *postexit*.

**Por que `game` existe:** o Wine funde os gatilhos num eixo Z único quando o SDL classifica o
dispositivo como gamepad, e o DirectInput de jogos antigos lê um gatilho em repouso no mínimo como
eixo empurrado até o fim. Botões fora da faixa de gamepad e repouso no centro resolvem os dois.
Detalhes e a análise do `speed.exe` estão no Vault (`~/Vault/nimbus`).

## Opções do daemon

`nimbus-linux --help`. As principais: `--profile`, `--identity`, `--home start|mode`, `--flip-y`,
`--no-grab`, `--led MÁSCARA` e `--monitor SEG` (mostra o relatório bruto e min/max por byte).

## Protocolo (17 bytes, sem Report ID)

| Bytes | Campo | Faixa |
|---|---|---|
| 0–3 | D-pad cima, direita, baixo, esquerda | uint8 (analógico, repouso 0) |
| 4–11 | A, B, X, Y, L1, R1, L2, R2 | uint8 (todos analógicos) |
| 12 | bit 0 = Home/Menu | |
| 13–16 | stick esq X/Y, dir X/Y | int8 −127..127, cima = positivo |

## Limitações conhecidas

- LEDs de jogador: o hidraw recusa a escrita (`EINVAL`), por isso `--led` vem desligado.
- Um módulo de kernel foi descartado (sem headers para o kernel em uso).

## Desenvolvimento

```sh
python3 -m unittest discover -s tests -v
```

A conversão relatório → eventos é uma função pura (`translate`) e tem testes; o resto fala com
`/dev/uinput` e o hidraw e precisa do controle.

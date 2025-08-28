# OT-sim + halucinator demo

## Building halucinator

- clone from: https://github.com/richyliu/halucinator
  - dev branch
- build openplc demo with: `docker build -t halucinator_openplc -f openplc_demo.Dockerfile .`

## Building OT-sim

- clone from: https://github.com/richyliu/ot-sim
  - dev-halucinator branch
- build with: docker build -t ot-sim .

## Running

Use docker-compose: `docker-compose up` from this directory. To tear down (including volumes), run `docker-compose down -v`.

## Demo details

- navigate to http://localhost:8000/ui for HMI
- halucinator communicates with the ot-sim halucinator plugin via IPC (unix domain sockets in `/tmp`)
- can paused program and attach to halucinator with: `docker attach otsimhalucinator_halucinator_openplc_1`

Commands for viewing memory and writing memory
```
addr = target.read_memory(target.regs.r0 + 0x10, size=4)
print(f'Memory at {addr:08x} is {target.read_memory(addr, 4)}')
target.write_memory(addr, size=4, value=0)
target.write_memory(addr, size=4, value=1)
```
(ctrl-p ctrl-q to detach), resume and see changes in HMI

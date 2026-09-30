{ pkgs, support }:
pkgs.testers.runNixOSTest {
  name = "graphics-without-existing-drivers";
  nodes.machine = {
    virtualisation.qemu.options = [
      "-vga none"
      "-device virtio-gpu-pci"
    ];
    # The test harness exposes a real Virtio PCI display device. Prevent its
    # driver from loading: PCI detection must still work, without /dev/dri.
    boot.blacklistedKernelModules = [ "virtio_gpu" ];
    environment.systemPackages = [
      pkgs.python3
      pkgs.kmod
    ];
  };
  testScript = ''
    machine.start()
    machine.wait_for_unit("multi-user.target")
    machine.succeed("test ! -d /sys/module/virtio_gpu")
    machine.succeed("cp -r ${../scripts} /tmp/installer; chmod -R u+w /tmp/installer")
    machine.succeed("PYTHONPATH=/tmp/installer python3 - <<'PY'\n"
                    "import importlib.util, json\n"
                    "from pathlib import Path\n"
                    "from graphics import resolve_graphics, validate_saved\n"
                    "spec = importlib.util.spec_from_file_location('installer', '/tmp/installer/install.py')\n"
                    "installer = importlib.util.module_from_spec(spec); spec.loader.exec_module(installer)\n"
                    "hardware = installer.detect_hardware()\n"
                    "support = json.loads(Path('${support}/graphics-support.json').read_text())\n"
                    "config = resolve_graphics(hardware['gpus'], support)\n"
                    "assert config['profile'] == 'virtual', config\n"
                    "assert config['devices'][0]['driver'] == 'virtio_gpu', config\n"
                    "assert validate_saved({'graphics': config}, config)['graphics'] == config\n"
                    "Path('/tmp/graphics.json').write_text(json.dumps(config))\nPY")
    # Query the guest's built module aliases without loading or binding it.
    machine.succeed("modprobe --resolve-alias virtio:d00000010v00001AF4 | grep -x virtio_gpu")
    machine.succeed("test ! -d /sys/module/virtio_gpu")
    machine.copy_from_machine("/tmp/graphics.json")
  '';
}

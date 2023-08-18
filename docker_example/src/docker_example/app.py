from docker_example.settings import DockerExampleSettings


def main():
    settings = DockerExampleSettings()
    print(f"docker-example!: {settings!r}") # noqa: T201


if __name__ == "__main__":
    main()

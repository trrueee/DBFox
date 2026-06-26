type DatasourceFormSecrets = {
  password: string;
  ssh_password: string;
  ssh_pkey_passphrase: string;
};

export function stripSensitiveDatasourceForm<T extends DatasourceFormSecrets>(form: T): T {
  return {
    ...form,
    password: "",
    ssh_password: "",
    ssh_pkey_passphrase: "",
  } as T;
}

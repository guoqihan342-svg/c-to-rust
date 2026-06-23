fn main() {
    match flashdb_rust::cli::run_from_env() {
        Ok(output) => {
            println!("{output}");
        }
        Err(err) => {
            eprintln!("{err}");
            std::process::exit(1);
        }
    }
}

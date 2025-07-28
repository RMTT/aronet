pub mod bird;
pub mod strongswan;

pub trait Daemon {
    fn runner(&self) -> impl Future<Output = ()>;
}

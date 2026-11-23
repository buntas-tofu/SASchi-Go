# Sieve of Eratosthenes over the complete pinned program's input domain.
limit <- 1000L
prime <- rep(TRUE, limit)
prime[1L] <- FALSE
for (candidate in 2L:limit) {
    if (prime[candidate] && 2L * candidate <= limit) {
        prime[seq.int(2L * candidate, limit, by = candidate)] <- FALSE
    }
}
writeLines(as.character(which(prime)))

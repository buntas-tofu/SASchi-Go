# Original base-R witnesses for bounded DATA events. No live SAS capture.
scenario <- commandArgs(trailingOnly=TRUE)[1]
if (scenario == 'snapshots') {
  raw <- data.frame(group=c(7,7,7,9), keep=c(0,1,1,1), amount=c(100,2,4,8))
  selected <- raw[raw$keep == 1, , drop=FALSE]
  start <- c(TRUE, diff(selected$group) != 0)
  finish <- c(diff(selected$group) != 0, TRUE)
  fee <- c(6,100)[1]
  total <- 0
  output <- list()
  for (i in seq_len(nrow(selected))) {
    if (start[i]) total <- 0
    total <- total + selected$amount[i]
    scratch <- if (i == 1) 17 else NA_real_
    snapshot <- data.frame(total=total, fee=fee, group=selected$group[i],
                           keep=selected$keep[i], amount=selected$amount[i], scratch=scratch)
    output[[length(output)+1]] <- snapshot
    snapshot$amount <- snapshot$amount + fee
    if (finish[i]) output[[length(output)+1]] <- snapshot
  }
  write.csv(do.call(rbind, output), stdout(), row.names=FALSE, na='')
} else if (scenario == 'filter') {
  group <- c(7,7,9)
  keep <- c(FALSE,TRUE,TRUE)
  where_group <- group[keep]
  where_first <- as.numeric(c(TRUE, diff(where_group) != 0))
  if_first <- as.numeric(c(TRUE, diff(group) != 0))[keep]
  write.csv(data.frame(where_first=where_first, if_first=if_first), stdout(), row.names=FALSE)
} else if (scenario == 'output') {
  x <- 13
  output <- c(x)
  x <- 29
  output <- c(output, x)
  x <- 47
  write.csv(data.frame(x=output), stdout(), row.names=FALSE)
} else stop('unknown scenario')

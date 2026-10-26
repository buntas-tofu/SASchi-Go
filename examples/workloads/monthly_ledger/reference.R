# Original independent vector/table model. Base R, no translator helpers.
# Status: repository workload witness for maintainer review, no live SAS.
args <- commandArgs(trailingOnly=TRUE)
stopifnot(length(args)==2L)
input <- args[1L]
output <- args[2L]
options(digits=17)
raw <- read.csv(file.path(input,"raw.csv"), colClasses="numeric", na.strings="NA")
lookup <- read.csv(file.path(input,"lookup.csv"), colClasses="numeric", na.strings="NA")

# Half-unit inputs make ties exact in binary64; rounded outputs are integers.
rounded <- raw[!is.na(raw$include) & raw$include==1, ,drop=FALSE]
rounded$amount <- sign(rounded$amount)*floor(abs(rounded$amount)+0.5)
ordered <- rounded[order(rounded$account, rounded$period, rounded$seq,
                         na.last=FALSE, method="radix"), ,drop=FALSE]
keys <- lookup[order(lookup$account, na.last=FALSE, method="radix"), ,drop=FALSE]
joined <- merge(ordered,keys,by="account",all=TRUE,sort=TRUE)
joined <- joined[order(joined$account,joined$period,joined$seq,
                       na.last=FALSE,method="radix"), names(c(raw,lookup["fee"])),drop=FALSE]
frame <- joined[!is.na(joined$period) & joined$period>0, ,drop=FALSE]
n <- nrow(frame)
previous <- change <- total <- numeric(n)
last <- logical(n)
if (n>0L) {
  first <- c(TRUE,tail(frame$account,-1L)!=head(frame$account,-1L))
  last <- c(head(frame$account,-1L)!=tail(frame$account,-1L),TRUE)
  previous <- c(NA_real_,head(frame$amount,-1L))
  change <- frame$amount-previous
  previous[first] <- change[first] <- NA_real_
  frame$amount[is.na(frame$amount)] <- 0
  running <- 0
  for (i in seq_len(n)) {
    if (first[i]) running <- 0
    running <- running+frame$amount[i]
    total[i] <- running
  }
}
band <- ifelse(frame$amount>=10,"high","base")
code <- if (n>0L) paste0(band,"-U") else character()
detail <- data.frame(band=band, code=code, entry_kind=rep("row  ",n),
                     total=total,frame,previous=previous,change=change,
                     adjusted=frame$amount+frame$fee,stringsAsFactors=FALSE)
indices <- rep(seq_len(n),times=ifelse(last,2L,1L))
snapshots <- detail[indices, ,drop=FALSE]
if (n>0L) snapshots$entry_kind <- unlist(lapply(last,function(z) {
  if (z) c("row  ","close") else "row  "
}),use.names=FALSE)
tables <- list(rounded=rounded,ordered=ordered,keys=keys,joined=joined,snapshots=snapshots)
dir.create(output,recursive=TRUE,showWarnings=FALSE)
for (name in names(tables)) {
  write.csv(tables[[name]],file.path(output,paste0(name,".csv")),row.names=FALSE,na="NA")
}

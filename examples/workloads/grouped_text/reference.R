# Original independent character/table model using base R only.
# Status: workload evidence for maintainer review, no live SAS.
args <- commandArgs(trailingOnly=TRUE)
stopifnot(length(args)==2L)
input <- args[1L]
output <- args[2L]
options(digits=17)
invisible(Sys.setlocale("LC_COLLATE","C"))

# Character NA is data. Only numeric columns interpret the NA marker.
raw <- read.csv(file.path(input,"raw.csv"),colClasses="character",
                na.strings=NULL,strip.white=FALSE,check.names=FALSE,
                stringsAsFactors=FALSE,comment.char="")
stopifnot(identical(names(raw),c("team","seq","include","payload","tag","note","value")))
for (name in c("seq","include","value")) {
  absent <- raw[[name]]=="NA"
  text <- raw[[name]]
  text[absent] <- "0"
  value <- as.numeric(text)
  stopifnot(all(is.finite(value)))
  value[absent] <- NA_real_
  raw[[name]] <- value
}
pad <- function(text,width) {
  stopifnot(!anyNA(text),all(nchar(text,type="bytes")<=width))
  sprintf(paste0("%-",width,"s"),text)
}
for (name in c("team","payload","tag","note")) {
  width <- c(team=12,payload=128,tag=24,note=64)[[name]]
  raw[[name]] <- pad(raw[[name]],width)
}

# An explicit source ordinal makes tied sort keys stable.
ordered <- raw[order(raw$team,raw$seq,seq_len(nrow(raw)),
                     na.last=FALSE,method="radix"), ,drop=FALSE]
frame <- ordered[!is.na(ordered$include) & ordered$include==1, ,drop=FALSE]
n <- nrow(frame)
short <- substr(frame$payload,1L,8L)
left <- trimws(frame$tag,whitespace=" ")
right <- trimws(short,whitespace=" ")
combined <- ifelse(left=="",right,ifelse(right=="",left,paste0(left,"|",right)))
backwards <- vapply(strsplit(frame$payload,"",fixed=TRUE),
                    function(chars) paste(rev(chars),collapse=""),character(1))
prepared <- data.frame(short=pad(short,8),combined=pad(combined,40),frame,
                       actual_len=nchar(sub(" +$","",frame$payload),type="bytes"),
                       storage_len=rep(128,n),backwards=backwards,
                       stringsAsFactors=FALSE,check.names=FALSE)

total <- positions <- numeric(n)
last <- logical(n)
if (n>0L) {
  first <- c(TRUE,tail(prepared$team,-1L)!=head(prepared$team,-1L))
  last <- c(head(prepared$team,-1L)!=tail(prepared$team,-1L),TRUE)
  prepared_value <- prepared$value
  prepared_value[is.na(prepared_value)] <- 0
  running <- position <- 0
  for (i in seq_len(n)) {
    if (first[i]) running <- position <- 0
    running <- running+prepared_value[i]
    position <- position+1
    total[i] <- running
    positions[i] <- position
  }
} else prepared_value <- numeric()
detail <- data.frame(entry_kind=rep("row  ",n),total=total,n_in_group=positions,
                      prepared,stringsAsFactors=FALSE,check.names=FALSE)
detail$value <- prepared_value
indices <- rep(seq_len(n),times=ifelse(last,2L,1L))
snapshots <- detail[indices, ,drop=FALSE]
if (n>0L) snapshots$entry_kind <- unlist(lapply(last,function(z) {
  if (z) c("row  ","close") else "row  "
}),use.names=FALSE)

dir.create(output,recursive=TRUE,showWarnings=FALSE)
for (name in c("raw","ordered","prepared","snapshots")) {
  write.csv(get(name),file.path(output,paste0(name,".csv")),row.names=FALSE,na="NA")
}

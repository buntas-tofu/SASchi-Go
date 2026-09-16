# Composed rounding, sort, and one-to-many merge fixture. Base R only.
# Status: repository fixture evidence, not a live-SAS observation.
raw <- data.frame(id=c(2,1,1), amount=c(2.5,-1.5,3.5))
lookup <- data.frame(id=c(3,1), flag=c(30,10))
raw$amount <- sign(raw$amount)*floor(abs(raw$amount)+0.5+1e-9)
raw <- raw[order(raw$id, method="radix"),]
lookup <- lookup[order(lookup$id, method="radix"),]
joined <- merge(raw,lookup,by="id",all=TRUE,sort=TRUE)
write.csv(joined,stdout(),row.names=FALSE,na="")

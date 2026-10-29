# B3 independent bit-product and complete-program witness.
# Repository/base-R evidence for maintainers; no live SAS.
limit <- 2147483647
capture <- function(pattern,text) {
  m <- regmatches(text,regexec(paste0('(?i)^',pattern,'$'),text,perl=TRUE))[[1]]
  if(length(m)) m[-1] else NULL
}
hex <- function(x) paste(sprintf('%02x',as.integer(charToRaw(x))),collapse='')
render <- function(x) if(is.na(x)) '.' else sprintf('%.17g',x)
bound <- function(kind,text) {
  if(kind=='missing') return(NA_real_)
  if(kind!='number') stop('ordinary numeric operand required')
  x <- suppressWarnings(as.numeric(text))
  if(!is.finite(x) || abs(x)>limit) stop('finite bounded operand required')
  x
}
parts <- function(x) {
  if(x==0) return(list(bits=integer(),power=0))
  h <- strsplit(sprintf('%a',abs(x)),'p',fixed=TRUE)[[1]]
  mantissa <- sub('^0x','',h[1]); dot <- regexpr('.',mantissa,fixed=TRUE)[1]
  fraction <- if(dot>0) nchar(mantissa)-dot else 0L
  digits <- strsplit(gsub('.','',mantissa,fixed=TRUE),'',fixed=TRUE)[[1]]
  table <- c('0000','0001','0010','0011','0100','0101','0110','0111',
             '1000','1001','1010','1011','1100','1101','1110','1111')
  bits <- as.integer(strsplit(paste(table[match(digits,c(as.character(0:9),letters[1:6]))],collapse=''),'',fixed=TRUE)[[1]])
  bits <- bits[min(which(bits==1L)):length(bits)]
  power <- as.numeric(h[2])-4*fraction
  while(tail(bits,1)==0L) {bits <- head(bits,-1);power <- power+1}
  list(bits=bits,power=power)
}
bit_product <- function(a,b) {
  # Bit positions and carries remain tiny exact integers even for106-bit products.
  x <- rev(a); y <- rev(b); digits <- integer(length(x)+length(y)+1L)
  for(i in which(x==1L)) for(j in which(y==1L)) digits[i+j-1L] <- digits[i+j-1L]+1L
  for(i in seq_len(length(digits)-1L)) {
    digits[i+1L] <- digits[i+1L]+digits[i]%/%2L
    digits[i] <- digits[i]%%2L
  }
  while(tail(digits,1)==0L) digits <- head(digits,-1)
  rev(digits)
}
multiply <- function(a,b) {
  for(x in c(a,b)) if(!is.na(x) && (!is.finite(x) || abs(x)>limit)) stop('range')
  if(is.na(a) || is.na(b)) return(NA_real_)
  q <- a*b
  if(!is.finite(q) || abs(q)>limit) stop('product range')
  if(a==0 || b==0) return(0)
  if(q==0) stop('underflow')
  ap <- parts(a);bp <- parts(b);qp <- parts(q)
  exact <- bit_product(ap$bits,bp$bits)
  if(!identical(exact,qp$bits) || ap$power+bp$power!=qp$power) stop('rounded product')
  q
}
add <- function(a,b,subtract=FALSE) {
  if(is.na(a) || is.na(b)) return(NA_real_)
  if(subtract) b <- -b
  s <- a+b; z <- s-a; residual <- (a-(s-z))+(b-z)
  if(!is.finite(s) || abs(s)>limit || residual!=0) stop('rounded or unbounded sum')
  if(s==0) 0 else s
}
scan_program <- function(path) {
  code <- paste(readLines(path,warn=FALSE),collapse='\n');chars <- strsplit(code,'',fixed=TRUE)[[1]]
  i <- 1L;n <- length(chars);statements <- character();buffer <- '';comment <- FALSE
  while(i<=n) {
    ch <- chars[i];after <- if(i<n) chars[i+1L] else ''
    if(comment) {
      if(ch=='*' && after=='/') {comment <- FALSE;i <- i+2L;buffer <- paste0(buffer,' ')} else i <- i+1L
    } else if(ch=='/' && after=='*') {comment <- TRUE;i <- i+2L}
    else if(ch %in% c("'",'"')) stop('character source outside numeric witness')
    else if(ch==';') {
      statement <- trimws(buffer);if(!nzchar(statement)) stop('null statement outside witness')
      statements <- c(statements,statement);buffer <- '';i <- i+1L
    } else {buffer <- paste0(buffer,ch);i <- i+1L}
  }
  if(comment || nzchar(trimws(buffer))) stop('unconsumed source')
  statements
}
parse_expr <- function(text) {
  pattern <- '[0-9]+(?:\\.[0-9]*)?(?:[eE][+-]?[0-9]+)?|\\.[0-9]+(?:[eE][+-]?[0-9]+)?|[a-z_]\\w*|[.()+*{}\\[\\]-]'
  tokens <- regmatches(tolower(text),gregexpr(pattern,tolower(text),perl=TRUE))[[1]]
  if(!length(tokens) || paste(tokens,collapse='')!=gsub('[[:space:]]','',tolower(text))) stop('expression tokens')
  at <- 1L
  take <- function(value=NULL) {
    if(at>length(tokens)) stop('expression ends early')
    x <- tokens[at];if(!is.null(value) && x!=value) stop('expression token required')
    at <<- at+1L;x
  }
  peek <- function() if(at<=length(tokens)) tokens[at] else ''
  primary <- function() {
    x <- take()
    if(x %in% c('+','-')) return(list(kind='unary',op=x,value=primary()))
    if(x=='(') {node <- expression();take(')');return(node)}
    if(x=='.') return(list(kind='number',value=NA_real_))
    if(grepl('^[0-9.]',x)) {
      n <- suppressWarnings(as.numeric(x));if(!is.finite(n) || abs(n)>limit) stop('literal bound')
      return(list(kind='number',value=n))
    }
    if(!grepl('^[a-z_]\\w*$',x,perl=TRUE)) stop('primary')
    if(x=='sum' && peek()=='(') {
      take('(');take('of');name <- take();take('{');take('*');take('}');take(')')
      return(list(kind='array_sum',name=name))
    }
    if(peek() %in% c('{','[')) {
      opening <- take();index <- expression();take(if(opening=='{') '}' else ']')
      return(list(kind='array_get',name=x,index=index))
    }
    list(kind='variable',name=x)
  }
  product <- function() {
    node <- primary()
    while(peek()=='*') {take('*');node <- list(kind='binary',op='*',left=node,right=primary())}
    node
  }
  expression <- function() {
    node <- product()
    while(peek() %in% c('+','-')) {op <- take();node <- list(kind='binary',op=op,left=node,right=product())}
    node
  }
  result <- expression();if(at<=length(tokens)) stop('unconsumed expression');result
}
program <- function(path) {
  statements <- scan_program(path);at <- 1L
  cat('STATEMENTS:',length(statements),'\n',sep='')
  while(at<=length(statements)) {
    head <- capture('data\\s+([a-z_]\\w*)',statements[at]);at <- at+1L
    if(is.null(head)) stop('DATA header required')
    name <- tolower(head);schema <- character();arrays <- list();explicit <- FALSE
    add_name <- function(n) {if(!(n %in% schema)) schema <<- c(schema,n)}
    discover <- function(expr) {
      if(expr$kind=='variable') add_name(expr$name)
      else if(expr$kind %in% c('array_get','array_sum')) {
        if(is.null(arrays[[expr$name]])) stop('array declaration required')
        if(expr$kind=='array_get') discover(expr$index)
      } else if(expr$kind=='binary') {discover(expr$left);discover(expr$right)}
      else if(expr$kind=='unary') discover(expr$value)
    }
    parse_body <- function(nested=FALSE) {
      body <- list()
      repeat {
        if(at>length(statements)) stop('missing step/loop terminator')
        text <- tolower(statements[at]);at <<- at+1L
        if(text=='end') {if(!nested) stop('unexpected END');return(body)}
        if(text=='run') {if(nested) stop('RUN inside loop');return(body)}
        decl <- capture('array\\s+([a-z_]\\w*)\\s*[\\{\\[(]([^}\\])]+)[}\\])]\\s*(.*)',text)
        loop <- capture('do\\s+([a-z_]\\w*)\\s*=\\s*([+-]?[0-9]+)\\s+to\\s+([+-]?[0-9]+)(?:\\s+by\\s+([+-]?[0-9]+))?',text)
        put <- capture('put\\s+([a-z_]\\w*(?:\\s+[a-z_]\\w*)*)',text)
        assignment <- capture('(.+?)\\s*=\\s*(.+)',text)
        if(!is.null(decl)) {
          if(nested || !is.null(arrays[[decl[1]]])) stop('array declaration position')
          words <- strsplit(trimws(decl[3]),'\\s+',perl=TRUE)[[1]];if(identical(words,'')) words <- character()
          range <- if(length(words)==1) capture('([a-z_]+)([0-9]+)-\\1([0-9]+)',words) else NULL
          if(!is.null(range)) words <- paste0(range[1],seq(as.integer(range[2]),as.integer(range[3])))
          if(decl[2]=='*') {lower <- 1L;upper <- length(words)}
          else if(grepl(':',decl[2],fixed=TRUE)) {bounds <- as.numeric(strsplit(decl[2],':',fixed=TRUE)[[1]]);lower <- bounds[1];upper <- bounds[2]}
          else {lower <- 1L;upper <- as.numeric(decl[2])}
          if(!length(words)) words <- paste0(decl[1],seq_len(upper-lower+1L))
          if(!is.finite(lower) || !is.finite(upper) || upper<lower || length(words)!=upper-lower+1L || anyDuplicated(words)) stop('array bounds/elements')
          arrays[[decl[1]]] <<- list(lower=lower,upper=upper,names=words)
          for(n in words) add_name(n)
          body[[length(body)+1L]] <- list(kind='declare')
        } else if(!is.null(loop)) {
          add_name(loop[1]);increment <- if(nzchar(loop[4])) as.numeric(loop[4]) else 1
          if(increment==0) stop('zero increment')
          body[[length(body)+1L]] <- list(kind='loop',name=loop[1],start=as.numeric(loop[2]),stop=as.numeric(loop[3]),increment=increment,body=parse_body(TRUE))
        } else if(!is.null(put)) {
          names <- strsplit(put,'\\s+',perl=TRUE)[[1]];for(n in names) add_name(n)
          body[[length(body)+1L]] <- list(kind='put',names=names)
        } else if(text=='output') {explicit <<- TRUE;body[[length(body)+1L]] <- list(kind='output')}
        else if(!is.null(assignment)) {
          target <- parse_expr(assignment[1]);value <- parse_expr(assignment[2])
          if(!(target$kind %in% c('variable','array_get'))) stop('assignment target')
          discover(target);discover(value);body[[length(body)+1L]] <- list(kind='assign',target=target,value=value)
        } else stop(paste('unhandled source statement',text))
      }
    }
    body <- parse_body();row <- setNames(as.list(rep(NA_real_,length(schema))),schema);output <- list();logs <- character();trips <- 0L
    evaluate <- function(expr) {
      if(expr$kind=='number') return(expr$value)
      if(expr$kind=='variable') return(row[[expr$name]])
      if(expr$kind=='unary') return(if(expr$op=='-') -evaluate(expr$value) else evaluate(expr$value))
      if(expr$kind=='binary') {
        a <- evaluate(expr$left);b <- evaluate(expr$right)
        return(if(expr$op=='*') multiply(a,b) else add(a,b,expr$op=='-'))
      }
      a <- arrays[[expr$name]]
      if(expr$kind=='array_sum') {
        values <- unlist(row[a$names]);if(all(is.na(values))) return(NA_real_)
        total <- 0;for(x in values[!is.na(values)]) total <- add(total,x)
        return(total)
      }
      index <- evaluate(expr$index)
      if(is.na(index) || index!=trunc(index) || index<a$lower || index>a$upper) stop('array index')
      row[[a$names[index-a$lower+1L]]]
    }
    perform <- function(body) {
      for(op in body) {
        if(op$kind=='declare') next
        if(op$kind=='assign') {
          value <- evaluate(op$value)
          if(op$target$kind=='variable') target <- op$target$name
          else {
            a <- arrays[[op$target$name]];index <- evaluate(op$target$index)
            if(is.na(index) || index!=trunc(index) || index<a$lower || index>a$upper) stop('write index')
            target <- a$names[index-a$lower+1L]
          }
          row[[target]] <<- value
        } else if(op$kind=='output') output[[length(output)+1L]] <<- row[schema]
        else if(op$kind=='put') {
          values <- unlist(row[op$names])
          if(any(!is.na(values) & (values!=trunc(values) | abs(values)>limit))) stop('integer PUT profile')
          logs <<- c(logs,paste0(paste(vapply(values,render,''),collapse=' '),' '))
        } else if(op$kind=='loop') {
          row[[op$name]] <<- op$start
          test <- function() if(op$increment>0) row[[op$name]]<=op$stop else row[[op$name]]>=op$stop
          while(test()) {trips <<- trips+1L;if(trips>10000L) stop('loop budget');perform(op$body);row[[op$name]] <<- row[[op$name]]+op$increment}
        } else stop('unhandled runtime operation')
      }
    }
    perform(body);if(!explicit) output[[1L]] <- row[schema]
    encode <- function(r) paste(vapply(r,render,''),collapse=',')
    cat('STEP:',name,'\n','SCHEMA:',paste(schema,collapse=','),'\n','TRIPS:',trips,'\n','FINAL:',encode(row[schema]),'\n',sep='')
    if(name!='_null_') for(snapshot in output) cat('ROW:',encode(snapshot),'\n',sep='')
    for(log in logs) cat('LOG:',hex(log),'\n',sep='')
  }
}
args <- commandArgs(trailingOnly=TRUE)
if(args[1]=='cases') {
  cases <- read.csv(args[2],colClasses='character',na.strings=NULL)
  for(i in seq_len(nrow(cases))) {
    r <- cases[i,]
    answer <- tryCatch({a <- bound(r$a_kind,r$a);b <- bound(r$b_kind,r$b);paste0('OK:',render(multiply(a,b)))},error=function(e) 'REFUSE')
    cat(r$id,':',answer,'\n',sep='')
  }
} else if(args[1]=='program') program(args[2]) else stop('unknown witness mode')
